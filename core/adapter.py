"""
配置适配器

将新配置系统（YAML + Pydantic）转换为回测引擎所需的配置对象。
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation

from .loader import ConfigLoader
from .models import (
    BackTestConfig,
    DataConfig,
    InstrumentConfig,
    InstrumentType,
    LegacyStrategyConfig,
    LogConfig,
    project_root,
)
from .schemas import ActiveConfig, EnvironmentConfig, StrategyConfig


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
        self._backtest_config_cache: BackTestConfig | None = None

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

    def create_instrument_config(self, symbol: str) -> InstrumentConfig:
        """根据符号创建 InstrumentConfig"""
        if ":" in symbol:
            raw_pair = symbol.split(":")[0]
        else:
            raw_pair = symbol

        base_currency = "USDT"
        quote_currency = raw_pair.replace(base_currency, "")

        return InstrumentConfig(
            venue_name=self.get_venue(),
            quote_currency=quote_currency,
            base_currency=base_currency,
            type=InstrumentType(self.env_config.trading.instrument_type),
        )

    def create_data_config(self, symbol: str, timeframe: str, label: str = "main") -> DataConfig:
        """创建数据配置"""
        safe_symbol = symbol.replace("/", "")
        filename = f"{self.get_venue().lower()}-{safe_symbol}-{timeframe}-{self.get_start_date()}_{self.get_end_date()}.csv"

        unit = timeframe[-1]
        period = int(timeframe[:-1]) if len(timeframe) > 1 else 1
        agg = (
            BarAggregation.MINUTE if unit == "m"
            else BarAggregation.HOUR if unit == "h"
            else BarAggregation.DAY
        )

        return DataConfig(
            csv_file_name=f"{safe_symbol}/{filename}",
            bar_aggregation=agg,
            bar_period=period,
            label=label,
        )

    def build_backtest_config(self) -> BackTestConfig:
        """构建回测配置"""
        if self._backtest_config_cache is not None:
            return self._backtest_config_cache

        # 数据限制检查（严格模式）
        # 注意：测试环境可通过环境变量 SKIP_DATA_LIMIT_CHECK=1 跳过检查
        import os
        if os.environ.get('SKIP_DATA_LIMIT_CHECK') != '1':
            from utils.data_limits import check_data_availability

            from .schemas import ConfigValidationError

            is_available, warning = check_data_availability(
                self.get_start_date(),
                self.get_end_date(),
                self.get_venue(),
                "oi"
            )

            if not is_available and warning:
                raise ConfigValidationError(
                    f"数据范围超出交易所限制\n\n{warning}\n\n"
                    f"请修改配置文件中的日期范围或切换交易所。"
                )

        final_instruments = []
        final_data_feeds = []

        params = self.strategy_config.parameters
        universe_file = params.get("universe_filename") or params.get("universe_filepath")

        if universe_file:
            u_path = Path(universe_file)
            if not u_path.is_absolute():
                u_path = project_root / "data" / u_path.name

            if u_path.exists():
                with open(u_path, "r") as f:
                    u_data = json.load(f)
                    universe_symbols = set()
                    for month_list in u_data.values():
                        universe_symbols.update(month_list)

                for symbol in sorted(universe_symbols):
                    raw_symbol = symbol.split(":")[0]
                    inst_cfg = self.create_instrument_config(symbol)
                    final_instruments.append(inst_cfg)

                    data_cfg = self.create_data_config(raw_symbol, self.get_main_timeframe(), "main")
                    data_cfg.instrument_id = inst_cfg.instrument_id
                    final_data_feeds.append(data_cfg)
            else:
                inst = self.create_instrument_config(self.get_primary_symbol())
                final_instruments.append(inst)
                final_data_feeds.append(
                    self.create_data_config(self.get_primary_symbol(), self.get_main_timeframe(), "main")
                )
        else:
            inst = self.create_instrument_config(self.get_primary_symbol())
            final_instruments.append(inst)

            main_cfg = self.create_data_config(self.get_primary_symbol(), self.get_main_timeframe(), "main")
            main_cfg.instrument_id = inst.instrument_id
            final_data_feeds.append(main_cfg)

            trend_cfg = self.create_data_config(self.get_primary_symbol(), self.get_trend_timeframe(), "trend")
            trend_cfg.instrument_id = inst.instrument_id
            final_data_feeds.append(trend_cfg)

        btc_exists = any(inst.quote_currency == "BTC" for inst in final_instruments)
        if not btc_exists:
            btc_inst = self.create_instrument_config("BTCUSDT")
            final_instruments.append(btc_inst)

        benchmark_cfg = self.create_data_config("BTCUSDT", self.get_main_timeframe(), "benchmark")
        btc_instrument_id = None
        for inst in final_instruments:
            if inst.quote_currency == "BTC":
                btc_instrument_id = inst.instrument_id
                benchmark_cfg.instrument_id = btc_instrument_id
                break
        final_data_feeds.append(benchmark_cfg)

        if btc_instrument_id:
            benchmark_trend_cfg = self.create_data_config("BTCUSDT", self.get_trend_timeframe(), "benchmark_trend")
            benchmark_trend_cfg.instrument_id = btc_instrument_id
            final_data_feeds.append(benchmark_trend_cfg)

        primary_instrument = final_instruments[0]

        params_dict = deepcopy(self.strategy_config.parameters)
        if self.active_config.overrides:
            strategy_overrides = self.active_config.overrides.get("strategy", {})
            if strategy_overrides:
                params_dict.update(strategy_overrides)

        if self.strategy_config.config_class:
            try:
                import importlib
                module = importlib.import_module(self.strategy_config.module_path)
                config_class = getattr(module, self.strategy_config.config_class)
                strategy_params = config_class(**params_dict)
            except Exception:
                strategy_params = params_dict
        else:
            strategy_params = params_dict

        strategy_cfg = LegacyStrategyConfig(
            name=self.strategy_config.name,
            module_path=self.strategy_config.module_path,
            config_class=self.strategy_config.config_class,
            params=strategy_params,
        )

        log_cfg = LogConfig(
            log_level=self.env_config.logging.level,
            log_level_file=self.env_config.logging.file_level,
            log_component_levels=self.env_config.logging.components,
            log_components_only=self.env_config.logging.components_only,
        )

        self._backtest_config_cache = BackTestConfig(
            instrument=primary_instrument,
            instruments=final_instruments,
            data_feeds=final_data_feeds,
            strategy=strategy_cfg,
            start_date=self.get_start_date(),
            end_date=self.get_end_date(),
            initial_balances=self.get_initial_balances(),
            logging=log_cfg,
        )

        return self._backtest_config_cache

    def reload(self):
        """重新加载配置"""
        self.active_config = self.loader.load_active_config()
        self.env_config = self.loader.load_environment_config(
            self.active_config.environment
        )
        self.strategy_config = self.loader.load_strategy_config(
            self.active_config.strategy
        )
        self._backtest_config_cache = None


_adapter = ConfigAdapter()


def get_adapter() -> ConfigAdapter:
    """获取全局配置适配器"""
    return _adapter
