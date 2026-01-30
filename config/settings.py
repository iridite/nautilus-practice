"""
配置系统统一接口

基于YAML + Pydantic的配置管理系统。
"""

from typing import List

from nautilus_trader.model import Money

from .adapter import ConfigAdapter, DataConfig, get_adapter

# ==========================================
# 全局配置适配器
# ==========================================

_adapter = get_adapter()

# ==========================================
# 配置访问接口
# ==========================================


def get_venue() -> str:
    """获取交易所名称"""
    return _adapter.get_venue()


def get_start_date() -> str:
    """获取回测开始日期"""
    return _adapter.get_start_date()


def get_end_date() -> str:
    """获取回测结束日期"""
    return _adapter.get_end_date()


def get_initial_balances() -> List[Money]:
    """获取初始余额"""
    return _adapter.get_initial_balances()


def get_main_timeframe() -> str:
    """获取主时间框架"""
    return _adapter.get_main_timeframe()


def get_trend_timeframe() -> str:
    """获取趋势时间框架"""
    return _adapter.get_trend_timeframe()


def get_primary_symbol() -> str:
    """获取主要交易对"""
    return _adapter.get_primary_symbol()


# ==========================================
# 配置构建函数
# ==========================================


def create_data_config(symbol: str, timeframe: str, label: str = "main") -> DataConfig:
    """创建数据配置"""
    from nautilus_trader.model.enums import BarAggregation

    unit = timeframe[-1]
    period = int(timeframe[:-1]) if len(timeframe) > 1 else 1
    agg = (
        BarAggregation.MINUTE if unit == "m"
        else BarAggregation.HOUR if unit == "h"
        else BarAggregation.DAY
    )

    venue = _adapter.get_venue().lower()
    safe_symbol = symbol.replace("/", "")
    start = _adapter.get_start_date()
    end = _adapter.get_end_date()
    filename = f"{venue}-{safe_symbol}-{timeframe}-{start}_{end}.csv"

    return DataConfig(
        csv_file_name=f"{safe_symbol}/{filename}",
        bar_aggregation=agg,
        bar_period=period,
        label=label,
    )


# ==========================================
# 配置管理功能
# ==========================================


def reload_config():
    """重新加载所有配置"""
    _adapter.reload()
    print("✅ 配置重新加载完成!")


def get_available_environments() -> List[str]:
    """获取可用的环境列表"""
    return _adapter.loader.paths.list_environments()


def get_available_strategies() -> List[str]:
    """获取可用的策略列表"""
    return _adapter.loader.paths.list_strategies()


def validate_config() -> dict:
    """验证当前配置"""
    return _adapter.loader.validate_config_files()


def print_config_summary():
    """打印配置摘要"""
    print("📋 当前配置摘要:")
    print(f"  环境: {_adapter.active_config.environment}")
    print(f"  策略: {_adapter.active_config.strategy}")
    print(f"  交易所: {get_venue()}")
    print(f"  主要交易对: {get_primary_symbol()}")
    print(f"  日期范围: {get_start_date()} 到 {get_end_date()}")
    print(f"  初始余额: {get_initial_balances()[0]}")
    print(f"  时间框架: {get_main_timeframe()} (主), {get_trend_timeframe()} (趋势)")


# ==========================================
# 配置对象访问（用于需要直接访问配置对象的场景）
# ==========================================


def get_adapter() -> ConfigAdapter:
    """获取配置适配器"""
    return _adapter


def build_backtest_config():
    """构建回测配置"""
    return _adapter.build_backtest_config()


def run_file_cleanup() -> int:
    """执行文件清理"""
    from pathlib import Path
    from utils.file_cleanup import auto_cleanup, FileCleanupConfig

    base_dir = Path(__file__).parent.parent
    fc = _adapter.env_config.file_cleanup
    config = FileCleanupConfig(
        max_files_per_dir=fc.max_files_per_dir,
        enabled=fc.enabled,
        target_dirs=fc.target_dirs,
    )
    return auto_cleanup(base_dir, config)


# ==========================================
# 初始化和启动信息
# ==========================================


def _print_startup_info():
    """打印启动信息"""
    try:
        print("🔧 配置系统已加载")
        print(f"   环境: {_adapter.active_config.environment}")
        print(f"   策略: {_adapter.active_config.strategy}")
        print(f"   配置目录: {_adapter.loader.paths.config_root}")
    except Exception as e:
        print(f"⚠️ 配置系统警告: {e}")


if __name__ != "__main__":
    _print_startup_info()

# ==========================================
# 导出接口
# ==========================================

__all__ = [
    "get_venue",
    "get_start_date",
    "get_end_date",
    "get_initial_balances",
    "get_main_timeframe",
    "get_trend_timeframe",
    "get_primary_symbol",
    "create_data_config",
    "reload_config",
    "get_available_environments",
    "get_available_strategies",
    "validate_config",
    "print_config_summary",
    "get_adapter",
    "run_file_cleanup",
    "build_backtest_config",
    "BackTestConfig",
    "DataConfig",
    "InstrumentConfig",
    "InstrumentType",
    "LegacyStrategyConfig",
]
