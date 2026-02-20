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

# Instrument helper imports are performed inside functions to avoid circular imports
# (importing them at module level caused a circular import when other utils modules
# import core.adapter). Local imports keep semantics identical while breaking the cycle.
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

    def _extract_symbols_from_universe(self, u_data: dict) -> set[str]:
        """从universe数据中提取符号集合"""
        symbols = set()
        for month_list in u_data.values():
            for symbol in month_list:
                if ":" in symbol:
                    symbols.add(symbol.split(":")[0])
                else:
                    symbols.add(symbol)
        return symbols

    def _get_universe_file_path(self, universe_top_n: int, universe_freq: str) -> Path:
        """获取universe文件路径"""
        return project_root / "data" / "universe" / f"universe_{universe_top_n}_{universe_freq}.json"

    def _raise_universe_not_found_error(self, universe_file: Path, universe_top_n: int, universe_freq: str):
        """抛出universe文件不存在错误"""
        available_files = sorted([f.stem for f in (project_root / "data" / "universe").glob("universe_*.json")])
        available_configs = [f.replace("universe_", "") for f in available_files]
        raise ConfigValidationError(
            f"配置的 Universe 文件不存在: {universe_file}\n"
            f"配置参数: universe_top_n={universe_top_n}, universe_freq={universe_freq}\n"
            f"可用的 Universe 配置: {', '.join(available_configs)}\n"
            f"请修改配置文件中的 universe_top_n 或 universe_freq 参数，或运行以下命令生成缺失的 Universe 文件：\n"
            f"  uv run python scripts/generate_universe.py"
        )

    def _load_universe_from_file(self, universe_file: Path) -> set[str]:
        """从文件加载universe符号"""
        with open(universe_file, "r") as f:
            u_data = json.load(f)
            return self._extract_symbols_from_universe(u_data)

    def _load_universe_by_top_n(self, params: dict) -> set[str] | None:
        """通过top_n参数加载universe"""
        universe_top_n = params.get("universe_top_n")
        if not universe_top_n:
            return None
        
        universe_freq = params.get("universe_freq", "ME")
        universe_file = self._get_universe_file_path(universe_top_n, universe_freq)
        
        if universe_file.exists():
            return self._load_universe_from_file(universe_file)
        else:
            self._raise_universe_not_found_error(universe_file, universe_top_n, universe_freq)

    def _load_universe_by_filename(self, params: dict) -> set[str] | None:
        """通过filename参数加载universe（兼容旧配置）"""
        universe_file = params.get("universe_filename") or params.get("universe_filepath")
        if not universe_file:
            return None

        u_path = Path(universe_file)
        if not u_path.is_absolute():
            u_path = project_root / "data" / u_path.name

        if not u_path.exists():
            raise ConfigValidationError(
                f"配置的 Universe 文件不存在: {u_path}\n"
                f"请检查配置文件中的 universe_filename 或 universe_filepath 参数"
            )

        return self._load_universe_from_file(u_path)

    def _load_universe_symbols(self) -> set[str] | None:
        """加载 universe 符号集合"""
        params = self.strategy_config.parameters

        # 优先使用 universe_top_n 参数
        symbols = self._load_universe_by_top_n(params)
        if symbols is not None:
            return symbols

        # 兼容旧的 universe_filename 参数
        return self._load_universe_by_filename(params)


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
        """从简化标的名称还原完整 instrument_id

        Delegate to `utils.instrument_helpers.format_aux_instrument_id`, while preserving
        the adapter's environment-driven semantics by passing venue and instrument type
        from the environment configuration.

        Falls back to original heuristic if helper fails for any reason.
        """
        # Local import to avoid circular dependency
        from utils.instrument_helpers import format_aux_instrument_id

        venue = self.get_venue()
        inst_type = self.env_config.trading.instrument_type

        try:
            # Use the helper which normalizes various aux symbol formats and composes
            # a canonical instrument_id. We explicitly pass env-driven inst_type and venue
            # to preserve adapter semantics.
            return format_aux_instrument_id(
                symbol,
                template_inst_id=None,
                venue=venue,
                inst_type=inst_type,
            )
        except Exception:
            # Fallback: preserve previous behavior in case of unexpected helper failure
            # 保持原有逻辑，确保在任何情况下都能返回有效的 instrument_id 字符串
            if symbol.endswith("USDT"):
                # ETHUSDT -> 永续合约 or spot
                if inst_type == "SWAP":
                    return f"{symbol}-PERP.{venue}"
                elif inst_type == "SPOT":
                    return f"{symbol}.{venue}"
            else:
                # ETH -> 现货
                return f"{symbol}USDT.{venue}"

            return f"{symbol}-PERP.{venue}"

    def _restore_bar_type(self, symbol: str, timeframe: str, price_type: str = "LAST", origination: str = "EXTERNAL") -> str:
        """从简化字段还原完整 bar_type

        Delegate to `utils.instrument_helpers.build_bar_type_from_timeframe`.
        """
        # Local import to avoid circular dependency
        from utils.instrument_helpers import build_bar_type_from_timeframe

        # First restore instrument_id using adapter semantics
        instrument_id = self._restore_instrument_id(symbol)

        try:
            return build_bar_type_from_timeframe(
                instrument_id,
                timeframe,
                price_type=price_type,
                origination=origination,
            )
        except Exception:
            # Fallback: preserve previous timeframe -> unit mapping logic
            unit = timeframe[-1].lower()
            period = timeframe[:-1] if len(timeframe) > 1 else "1"

            unit_map = {
                "m": "MINUTE",
                "h": "HOUR",
                "d": "DAY"
            }

            bar_unit = unit_map.get(unit, "DAY")
            return f"{instrument_id}-{period}-{bar_unit}-{price_type.upper()}-{origination.upper()}"

    def _restore_single_instrument(self, params_dict: dict, symbol_key: str, instrument_key: str) -> None:
        """还原单个instrument_id"""
        if symbol_key in params_dict and not params_dict.get(instrument_key):
            params_dict[instrument_key] = self._restore_instrument_id(params_dict[symbol_key])

    def _restore_bar_type_if_needed(self, params_dict: dict, symbol_key: str) -> None:
        """如果需要，还原bar_type"""
        if symbol_key in params_dict and "timeframe" in params_dict and not params_dict.get("bar_type"):
            params_dict["bar_type"] = self._restore_bar_type(
                params_dict[symbol_key],
                params_dict["timeframe"],
                params_dict.get("price_type", "LAST"),
                params_dict.get("origination", "EXTERNAL")
            )

    def _apply_strategy_overrides(self, params_dict: dict) -> None:
        """应用active.yaml的strategy overrides"""
        if self.active_config.overrides:
            strategy_overrides = self.active_config.overrides.get("strategy", {})
            if strategy_overrides:
                params_dict.update(strategy_overrides)

    def _instantiate_config_class(self, params_dict: dict) -> Any:
        """实例化策略配置类"""
        if not self.strategy_config.config_class:
            return params_dict
        
        try:
            import importlib
            module = importlib.import_module(self.strategy_config.module_path)
            config_class = getattr(module, self.strategy_config.config_class)
            return config_class(**params_dict)
        except Exception:
            return params_dict

    def _build_strategy_params(self) -> Any:
        """构建策略参数"""
        params_dict = deepcopy(self.strategy_config.parameters)
        
        # 还原基础instrument_id和bar_type
        self._restore_single_instrument(params_dict, "symbol", "instrument_id")
        self._restore_bar_type_if_needed(params_dict, "symbol")
        
        # 还原btc相关
        self._restore_single_instrument(params_dict, "btc_symbol", "btc_instrument_id")
        
        # 还原pairs相关 (for kalman_pairs)
        self._restore_single_instrument(params_dict, "symbol_a", "instrument_a_id")
        self._restore_single_instrument(params_dict, "symbol_b", "instrument_b_id")
        self._restore_bar_type_if_needed(params_dict, "symbol_a")
        
        # 应用overrides
        self._apply_strategy_overrides(params_dict)
        
        # 实例化配置类
        return self._instantiate_config_class(params_dict)



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
