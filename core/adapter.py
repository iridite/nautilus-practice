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
from nautilus_trader.model.enums import BarAggregation, PriceType

from .exceptions import ConfigValidationError
from .loader import ConfigLoader
from .schemas import (
    ActiveConfig,
    BacktestConfig,
    DataConfig,
    EnvironmentConfig,
    InstrumentConfig,
    InstrumentType,
    LegacyStrategyConfig,
    LogConfig,
    StrategyConfig,
    project_root,
)


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
        self._backtest_config_cache: BacktestConfig | None = None

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
        # active.yaml 的 timeframe 优先覆盖环境配置
        return self.active_config.timeframe or self.env_config.trading.main_timeframe

    def get_trend_timeframe(self) -> str:
        return self.env_config.trading.trend_timeframe

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

        # 使用 active.yaml 的 price_type 配置（如果有）
        price_type = PriceType.LAST
        if self.active_config.price_type:
            price_type = PriceType[self.active_config.price_type]

        # 使用 active.yaml 的 origination 配置（如果有）
        origination = "EXTERNAL"
        if self.active_config.origination:
            origination = self.active_config.origination

        return DataConfig(
            csv_file_name=f"{safe_symbol}/{filename}",
            bar_aggregation=agg,
            bar_period=period,
            price_type=price_type,
            origination=origination,
            label=label,
        )

    def get_required_timeframes(self) -> List[str]:
        """获取策略声明的时间框架需求"""
        timeframes = self.strategy_config.parameters.get('timeframes', [])
        if not timeframes:
            return ["main"]
        return timeframes

    def _load_universe_symbols(self) -> set[str] | None:
        """加载 universe 符号集合"""
        params = self.strategy_config.parameters
        universe_file = params.get("universe_filename") or params.get("universe_filepath")

        if not universe_file:
            return None

        u_path = Path(universe_file)
        if not u_path.is_absolute():
            u_path = project_root / "data" / u_path.name

        if not u_path.exists():
            return None

        with open(u_path, "r") as f:
            u_data = json.load(f)
            symbols = set()
            for month_list in u_data.values():
                symbols.update(month_list)
            return symbols

    def _create_data_feeds_for_symbol(self, symbol: str, inst_cfg: InstrumentConfig) -> List[DataConfig]:
        """为单个标的创建数据流"""
        feeds = []
        raw_symbol = symbol.split(":")[0]
        required_timeframes = self.get_required_timeframes()

        for tf_label in required_timeframes:
            if tf_label == "main":
                tf_value = self.get_main_timeframe()
            elif tf_label == "trend":
                tf_value = self.get_trend_timeframe()
            else:
                continue

            data_cfg = self.create_data_config(raw_symbol, tf_value, tf_label)
            data_cfg.instrument_id = inst_cfg.instrument_id
            feeds.append(data_cfg)

        return feeds

    def _ensure_benchmark_instrument(self, instruments: List[InstrumentConfig]) -> InstrumentConfig:
        """确保 BTC benchmark 标的存在"""
        for inst in instruments:
            if inst.quote_currency == "BTC":
                return inst

        btc_inst = self.create_instrument_config("BTCUSDT")
        instruments.append(btc_inst)
        return btc_inst

    def _create_benchmark_feeds(self, btc_instrument_id: str) -> List[DataConfig]:
        """创建 benchmark 数据流"""
        feeds = []
        required_timeframes = self.get_required_timeframes()

        for tf_label in required_timeframes:
            if tf_label == "main":
                tf_value = self.get_main_timeframe()
                label = "benchmark"
            elif tf_label == "trend":
                tf_value = self.get_trend_timeframe()
                label = "benchmark_trend"
            else:
                continue

            cfg = self.create_data_config("BTCUSDT", tf_value, label)
            cfg.instrument_id = btc_instrument_id
            feeds.append(cfg)

        return feeds

    def _restore_instrument_id(self, symbol: str) -> str:
        """从简化标的名称还原完整 instrument_id"""
        venue = self.get_venue()
        inst_type = self.env_config.trading.instrument_type

        # 判断是现货还是永续
        if symbol.endswith("USDT"):
            # ETHUSDT -> 永续合约
            if inst_type == "SWAP":
                return f"{symbol}-PERP.{venue}"
            elif inst_type == "SPOT":
                return f"{symbol}.{venue}"
        else:
            # ETH -> 现货
            return f"{symbol}USDT.{venue}"

        return f"{symbol}-PERP.{venue}"

    def _restore_bar_type(self, symbol: str, timeframe: str, price_type: str = "LAST", origination: str = "EXTERNAL") -> str:
        """从简化字段还原完整 bar_type"""
        instrument_id = self._restore_instrument_id(symbol)

        # 转换 timeframe 格式: "1d" -> "1-DAY"
        unit = timeframe[-1].lower()
        period = timeframe[:-1] if len(timeframe) > 1 else "1"

        unit_map = {
            "m": "MINUTE",
            "h": "HOUR",
            "d": "DAY"
        }

        bar_unit = unit_map.get(unit, "DAY")
        return f"{instrument_id}-{period}-{bar_unit}-{price_type.upper()}-{origination.upper()}"

    def _build_strategy_params(self) -> Any:
        """构建策略参数"""
        params_dict = deepcopy(self.strategy_config.parameters)

        # 配置还原：从简化字段生成完整字段
        if "symbol" in params_dict and not params_dict.get("instrument_id"):
            params_dict["instrument_id"] = self._restore_instrument_id(params_dict["symbol"])

        if "symbol" in params_dict and "timeframe" in params_dict and not params_dict.get("bar_type"):
            params_dict["bar_type"] = self._restore_bar_type(
                params_dict["symbol"],
                params_dict["timeframe"],
                params_dict.get("price_type", "LAST"),
                params_dict.get("origination", "EXTERNAL")
            )

        # 还原 btc_symbol -> btc_instrument_id
        if "btc_symbol" in params_dict and not params_dict.get("btc_instrument_id"):
            params_dict["btc_instrument_id"] = self._restore_instrument_id(params_dict["btc_symbol"])

        # 还原 symbol_a/symbol_b -> instrument_a_id/instrument_b_id (for kalman_pairs)
        if "symbol_a" in params_dict and not params_dict.get("instrument_a_id"):
            params_dict["instrument_a_id"] = self._restore_instrument_id(params_dict["symbol_a"])

        if "symbol_b" in params_dict and not params_dict.get("instrument_b_id"):
            params_dict["instrument_b_id"] = self._restore_instrument_id(params_dict["symbol_b"])

        # 还原 bar_type for kalman_pairs (使用 symbol_a 作为主标的)
        if "symbol_a" in params_dict and "timeframe" in params_dict and not params_dict.get("bar_type"):
            params_dict["bar_type"] = self._restore_bar_type(
                params_dict["symbol_a"],
                params_dict["timeframe"],
                params_dict.get("price_type", "LAST"),
                params_dict.get("origination", "EXTERNAL")
            )

        # 应用 active.yaml 的 strategy overrides（仅用于调试）
        if self.active_config.overrides:
            strategy_overrides = self.active_config.overrides.get("strategy", {})
            if strategy_overrides:
                params_dict.update(strategy_overrides)

        if self.strategy_config.config_class:
            try:
                import importlib
                module = importlib.import_module(self.strategy_config.module_path)
                config_class = getattr(module, self.strategy_config.config_class)
                return config_class(**params_dict)
            except Exception:
                return params_dict

        return params_dict

    def _check_data_limits(self):
        """检查数据限制"""
        import os
        if os.environ.get('SKIP_DATA_LIMIT_CHECK') == '1':
            return

        data_types = self.strategy_config.parameters.get('data_types', [])
        if 'oi' not in data_types:
            return

        from utils.data_management.data_limits import check_data_availability

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

    def build_backtest_config(self) -> BacktestConfig:
        """构建回测配置"""
        if self._backtest_config_cache is not None:
            return self._backtest_config_cache

        self._check_data_limits()

        instruments = []
        data_feeds = []

        # 从策略配置读取交易对象列表
        symbols = self._get_trading_symbols()

        for symbol in symbols:
            inst_cfg = self.create_instrument_config(symbol)
            instruments.append(inst_cfg)
            data_feeds.extend(self._create_data_feeds_for_symbol(symbol, inst_cfg))

        # 确保 benchmark 标的存在并创建数据流
        btc_inst = self._ensure_benchmark_instrument(instruments)
        data_feeds.extend(self._create_benchmark_feeds(btc_inst.instrument_id))

        # 构建配置对象
        self._backtest_config_cache = BacktestConfig(
            instrument=instruments[0],
            instruments=instruments,
            data_feeds=data_feeds,
            strategy=LegacyStrategyConfig(
                name=self.strategy_config.name,
                module_path=self.strategy_config.module_path,
                config_class=self.strategy_config.config_class,
                params=self._build_strategy_params(),
            ),
            start_date=self.get_start_date(),
            end_date=self.get_end_date(),
            initial_balances=self.get_initial_balances(),
            logging=LogConfig(
                log_level=self.env_config.logging.level,
                log_level_file=self.env_config.logging.file_level,
                log_component_levels=self.env_config.logging.components,
                log_components_only=self.env_config.logging.components_only,
            ),
        )

        return self._backtest_config_cache

    def _get_trading_symbols(self) -> List[str]:
        """从策略配置获取交易对象列表"""
        params = self.strategy_config.parameters

        # 优先使用 universe
        universe_symbols = self._load_universe_symbols()
        if universe_symbols:
            return sorted(universe_symbols)

        # 其次使用 symbols 列表
        if "symbols" in params:
            symbols = params["symbols"]
            if isinstance(symbols, list):
                return symbols
            return [symbols]

        # 最后使用单个 symbol
        if "symbol" in params:
            return [params["symbol"]]

        raise ConfigValidationError("策略配置中必须指定 symbols 或 symbol")

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
