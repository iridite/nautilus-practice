"""
配置适配器

提供从新配置系统到旧接口的适配，用于渐进式迁移。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation, PriceType

from .loader import ConfigLoader
from .schemas import ActiveConfig, EnvironmentConfig, StrategyConfig


# 保留必要的枚举和工具类
project_root: Path = Path(__file__).parent.parent.resolve()


@dataclass
class DataConfig:
    """数据配置（简化版）"""
    csv_file_name: str
    bar_aggregation: BarAggregation = BarAggregation.HOUR
    bar_period: int = 1
    price_type: PriceType = PriceType.LAST
    instrument_id: str | None = None
    label: str = "main"

    @property
    def full_path(self) -> Path:
        return project_root / "data" / "raw" / self.csv_file_name

    @property
    def bar_type_str(self) -> str:
        return f"{self.bar_period}-{self.bar_aggregation.name}-{self.price_type.name}-EXTERNAL"


class ConfigAdapter:
    """配置适配器：将新配置系统转换为旧接口"""

    def __init__(self):
        self.loader = ConfigLoader()
        self.active_config: ActiveConfig = self.loader.load_active_config()
        self.env_config: EnvironmentConfig = self.loader.load_environment_config(
            self.active_config.environment
        )
        self.strategy_config: StrategyConfig = self.loader.load_strategy_config(
            self.active_config.strategy
        )

    def get_venue(self) -> str:
        return self.env_config.trading.venue

    def get_start_date(self) -> str:
        return self.env_config.backtest.start_date

    def get_end_date(self) -> str:
        return self.env_config.backtest.end_date

    def get_initial_balances(self) -> List[Money]:
        balance = self.env_config.trading.initial_balance
        return [Money(str(balance), USDT)]

    def get_main_timeframe(self) -> str:
        return self.env_config.timeframes.main

    def get_trend_timeframe(self) -> str:
        return self.env_config.timeframes.trend

    def get_primary_symbol(self) -> str:
        return self.active_config.primary_symbol

    def get_strategy_name(self) -> str:
        return self.strategy_config.name

    def get_strategy_module_path(self) -> str:
        return self.strategy_config.module_path

    def get_strategy_config_class(self) -> str:
        return self.strategy_config.config_class or f"{self.strategy_config.name}Config"

    def get_strategy_parameters(self) -> Dict[str, Any]:
        return self.strategy_config.parameters

    def reload(self):
        """重新加载配置"""
        self.active_config = self.loader.load_active_config()
        self.env_config = self.loader.load_environment_config(
            self.active_config.environment
        )
        self.strategy_config = self.loader.load_strategy_config(
            self.active_config.strategy
        )


# 全局适配器实例
_adapter = ConfigAdapter()


def get_adapter() -> ConfigAdapter:
    """获取全局配置适配器"""
    return _adapter
