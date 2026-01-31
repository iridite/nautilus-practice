"""
配置系统统一接口

基于YAML + Pydantic的配置管理系统。
"""

from typing import List

from .adapter import ConfigAdapter, DataConfig, get_adapter
from .models import (
    BackTestConfig,
    InstrumentConfig,
    InstrumentType,
    LegacyStrategyConfig,
)

# ==========================================
# 全局配置适配器
# ==========================================

_adapter = get_adapter()

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
    print(f"  交易所: {_adapter.get_venue()}")
    print(f"  主要交易对: {_adapter.get_primary_symbol()}")
    print(f"  日期范围: {_adapter.get_start_date()} 到 {_adapter.get_end_date()}")
    print(f"  初始余额: {_adapter.get_initial_balances()[0]}")
    print(f"  时间框架: {_adapter.get_main_timeframe()} (主), {_adapter.get_trend_timeframe()} (趋势)")


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

    from utils.file_cleanup import auto_cleanup

    base_dir = Path(__file__).parent.parent
    fc = _adapter.env_config.file_cleanup
    return auto_cleanup(
        base_dir,
        max_files_per_dir=fc.max_files_per_dir,
        enabled=fc.enabled,
        target_dirs=fc.target_dirs,
    )


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
    "get_adapter",
    "create_data_config",
    "reload_config",
    "get_available_environments",
    "get_available_strategies",
    "validate_config",
    "print_config_summary",
    "build_backtest_config",
    "run_file_cleanup",
    "BackTestConfig",
    "DataConfig",
    "InstrumentConfig",
    "InstrumentType",
    "LegacyStrategyConfig",
]
