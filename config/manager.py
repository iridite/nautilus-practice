"""
配置管理器

统一的配置访问接口，替换现有的settings.py功能。
提供与现有系统的兼容性，支持配置热重载和缓存。
"""

from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation

from utils.file_cleanup import FileCleanupConfig as FileCleanupUtil
from utils.file_cleanup import auto_cleanup

from .definitions import (
    BackTestConfig,
    DataConfig,
    InstrumentConfig,
    InstrumentType,
    LegacyStrategyConfig,
    LogConfig,
    project_root,
)
from .loader import ConfigLoader
from .schemas import (
    ActiveConfig,
    ConfigValidationError,
    EnvironmentConfig,
    StrategyConfig,
)


class ConfigManager:
    """
    配置管理器

    提供统一的配置访问接口，替换现有的settings.py功能。
    支持配置热重载、缓存和向后兼容性。
    """

    def __init__(self, config_dir: Optional[Path] = None, auto_load: bool = True):
        """
        初始化配置管理器

        Args:
            config_dir: 配置文件目录，默认为项目根目录下的config
            auto_load: 是否自动加载配置
        """
        self.loader = ConfigLoader(config_dir)
        self.paths = self.loader.paths

        # 配置缓存
        self._env_config: Optional[EnvironmentConfig] = None
        self._strategy_config: Optional[StrategyConfig] = None
        self._active_config: Optional[ActiveConfig] = None

        # 兼容性缓存
        self._backtest_config: Optional[BackTestConfig] = None

        if auto_load:
            self.reload()

    def reload(self):
        """重新加载所有配置"""
        try:
            # 清除缓存
            self._clear_cache()

            # 加载配置
            self._active_config = self.loader.load_active_config()
            self._env_config = self.loader.load_environment_config(
                self._active_config.environment
            )
            self._strategy_config = self.loader.load_strategy_config(
                self._active_config.strategy
            )

            # 清除兼容性缓存
            self._backtest_config = None

        except Exception as e:
            raise ConfigValidationError(f"Failed to reload configuration: {str(e)}")

    def _clear_cache(self):
        """清除配置缓存"""
        self._env_config = None
        self._strategy_config = None
        self._active_config = None
        self._backtest_config = None

    # ==========================================
    # 基础配置访问接口
    # ==========================================

    @property
    def env_config(self) -> EnvironmentConfig:
        """获取环境配置"""
        if self._env_config is None:
            raise ConfigValidationError("Environment config not loaded")
        return self._env_config

    @property
    def strategy_config(self) -> StrategyConfig:
        """获取策略配置"""
        if self._strategy_config is None:
            raise ConfigValidationError("Strategy config not loaded")
        return self._strategy_config

    @property
    def active_config(self) -> ActiveConfig:
        """获取活跃配置"""
        if self._active_config is None:
            raise ConfigValidationError("Active config not loaded")
        return self._active_config

    # ==========================================
    # 兼容性接口 - 替换settings.py中的变量
    # ==========================================

    @property
    def VENUE(self) -> str:
        """交易所名称"""
        return self.env_config.trading.venue

    @property
    def INSTRUMENT_TYPE(self) -> InstrumentType:
        """交易工具类型"""
        return InstrumentType(self.env_config.trading.instrument_type)

    @property
    def START_DATE(self) -> str:
        """回测开始日期"""
        return self.env_config.backtest.start_date

    @property
    def END_DATE(self) -> str:
        """回测结束日期"""
        return self.env_config.backtest.end_date

    @property
    def INITIAL_BALANCES(self) -> List[Money]:
        """初始余额"""
        balance = self.env_config.trading.initial_balance
        currency = self.env_config.trading.currency
        if currency == "USDT":
            return [Money(str(balance), USDT)]
        else:
            # 如果是其他货币，需要动态创建Currency对象
            # 这里简化处理，默认使用USDT
            return [Money(str(balance), USDT)]

    @property
    def MAIN_TIMEFRAME(self) -> str:
        """主时间框架"""
        return self.env_config.timeframes.main

    @property
    def TREND_TIMEFRAME(self) -> str:
        """趋势时间框架"""
        return self.env_config.timeframes.trend

    @property
    def PRIMARY_SYMBOL(self) -> str:
        """主要交易对"""
        return self.active_config.primary_symbol

    @property
    def ACTIVE_STRATEGY(self) -> LegacyStrategyConfig:
        """当前活跃策略（兼容格式）"""
        return self._build_legacy_strategy_config()

    @property
    def FILE_CLEANUP_CONFIG(self) -> FileCleanupUtil:
        """文件清理配置"""
        fc = self.env_config.file_cleanup
        return FileCleanupUtil(
            max_files_per_dir=fc.max_files_per_dir,
            enabled=fc.enabled,
            target_dirs=fc.target_dirs,
        )

    # ==========================================
    # 兼容性接口 - 替换settings.py中的函数
    # ==========================================

    def create_data_cfg(
        self, symbol: str, timeframe: str, label: str = "main"
    ) -> DataConfig:
        """
        统一生成符合项目路径规范的 DataConfig

        Args:
            symbol: 交易对符号
            timeframe: 时间框架
            label: 数据标签

        Returns:
            DataConfig: 数据配置对象
        """
        # 只有在 universe 接管的时候，系统才能自动生成 DataConfig，故其他模式下需要自行配置
        # 格式：BTCUSDT/BINANCE-BTCUSDT-1h-2024-01-01_2024-12-31.csv
        safe_symbol = symbol.replace("/", "")
        filename = f"{self.VENUE.lower()}-{safe_symbol}-{timeframe}-{self.START_DATE}_{self.END_DATE}.csv"

        # 提取时间周期详情
        unit = timeframe[-1]
        period = int(timeframe[:-1]) if len(timeframe) > 1 else 1
        agg = (
            BarAggregation.MINUTE
            if unit == "m"
            else BarAggregation.HOUR
            if unit == "h"
            else BarAggregation.DAY
        )

        return DataConfig(
            csv_file_name=f"{safe_symbol}/{filename}",
            bar_aggregation=agg,
            bar_period=period,
            label=label,
            instrument_id=None,  # 由引擎在运行时动态绑定
        )

    def create_instrument_cfg(self, symbol: str) -> InstrumentConfig:
        """
        根据符号创建 InstrumentConfig。
        支持格式: "SOLUSDT", "SOLUSDT:USDT", "SOL"

        Args:
            symbol: 交易对符号

        Returns:
            InstrumentConfig: 交易工具配置
        """
        # 解析符号
        if ":" in symbol:
            raw_pair = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT
        else:
            raw_pair = symbol

        # 提取 quote_currency (如 SOLUSDT -> SOL, BTCUSDT -> BTC)
        base_currency = "USDT"
        quote_currency = raw_pair.replace(base_currency, "")

        return InstrumentConfig(
            venue_name=self.VENUE,
            quote_currency=quote_currency,
            base_currency=base_currency,
            type=self.INSTRUMENT_TYPE,
        )

    def load_universe_symbols(self, universe_file: str) -> set:
        """
        从 Universe 文件加载所有符号。

        Args:
            universe_file: Universe 文件路径 (可以是绝对路径或相对于 data 目录的路径)

        Returns:
            set: 所有唯一符号的集合
        """
        import json

        u_path = Path(universe_file)
        if not u_path.is_absolute():
            u_path = project_root / "data" / u_path.name

        if not u_path.exists():
            print(f"⚠️ Universe file not found: {u_path}")
            return set()

        try:
            with open(u_path, "r") as f:
                u_data = json.load(f)
                symbols = set()
                for month_list in u_data.values():
                    symbols.update(month_list)
                return symbols
        except Exception as e:
            print(f"⚠️ Failed to load universe file: {e}")
            return set()

    def build_config(self) -> BackTestConfig:
        """
        构建回测配置，替换settings.build_config()

        Returns:
            BackTestConfig: 完整的回测配置
        """
        if self._backtest_config is not None:
            return self._backtest_config

        # 1. 初始化列表
        final_instruments = []
        final_data_feeds = []

        # 2. 检查策略是否带有 Universe
        params = self.strategy_config.parameters
        universe_file = params.get("universe_filename") or params.get(
            "universe_filepath"
        )

        if universe_file:
            # --- 多标的模式 ---
            print(f"🌐 Building Multi-Asset Config from {universe_file}...")

            # 加载 Universe 中的所有符号
            universe_symbols = self.load_universe_symbols(universe_file)

            if universe_symbols:
                print(
                    f"🌌 Universe loaded: {len(universe_symbols)} unique symbols found."
                )

                # 为每个符号创建 InstrumentConfig 和 DataConfig
                for symbol in sorted(universe_symbols):
                    raw_symbol = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT

                    # 创建 InstrumentConfig
                    inst_cfg = self.create_instrument_cfg(symbol)
                    final_instruments.append(inst_cfg)

                    # 创建主数据流 (main)
                    data_cfg = self.create_data_cfg(
                        raw_symbol, self.MAIN_TIMEFRAME, "main"
                    )
                    # 绑定 instrument_id 到 data_cfg
                    data_cfg.instrument_id = inst_cfg.instrument_id
                    final_data_feeds.append(data_cfg)
            else:
                print(
                    "⚠️ No symbols found in universe, falling back to single-asset mode."
                )
                # 回退到单标的模式
                inst = self.create_instrument_cfg(self.PRIMARY_SYMBOL)
                final_instruments.append(inst)
                final_data_feeds.append(
                    self.create_data_cfg(
                        self.PRIMARY_SYMBOL, self.MAIN_TIMEFRAME, "main"
                    )
                )
        else:
            # --- 单标的模式 ---
            print(f"🎯 Building Single-Asset Config for {self.PRIMARY_SYMBOL}...")
            inst = self.create_instrument_cfg(self.PRIMARY_SYMBOL)
            final_instruments.append(inst)

            # 添加数据流
            main_cfg = self.create_data_cfg(
                self.PRIMARY_SYMBOL, self.MAIN_TIMEFRAME, "main"
            )
            main_cfg.instrument_id = inst.instrument_id
            final_data_feeds.append(main_cfg)

            trend_cfg = self.create_data_cfg(
                self.PRIMARY_SYMBOL, self.TREND_TIMEFRAME, "trend"
            )
            trend_cfg.instrument_id = inst.instrument_id
            final_data_feeds.append(trend_cfg)

        # 3. 无论什么策略，通常都需要一个 Benchmark (如 BTC)
        # 检查 BTC 是否已经在列表中
        btc_exists = any(inst.quote_currency == "BTC" for inst in final_instruments)
        if not btc_exists:
            btc_inst = self.create_instrument_cfg("BTCUSDT")
            final_instruments.append(btc_inst)

        # 添加 benchmark 数据流 (1h 用于 RS 计算)
        benchmark_cfg = self.create_data_cfg(
            "BTCUSDT", self.MAIN_TIMEFRAME, "benchmark"
        )
        # 找到 BTC 的 instrument_id
        btc_instrument_id = None
        for inst in final_instruments:
            if inst.quote_currency == "BTC":
                btc_instrument_id = inst.instrument_id
                benchmark_cfg.instrument_id = btc_instrument_id
                break
        final_data_feeds.append(benchmark_cfg)

        # 添加 benchmark_trend 数据流 (4h 用于趋势过滤)
        if btc_instrument_id:
            benchmark_trend_cfg = self.create_data_cfg(
                "BTCUSDT", self.TREND_TIMEFRAME, "benchmark_trend"
            )
            benchmark_trend_cfg.instrument_id = btc_instrument_id
            final_data_feeds.append(benchmark_trend_cfg)

        # 4. 选择主标的 (用于兼容单标的模式的旧代码)
        # 在多标的模式下，选择第一个作为"主标的"用于兼容性
        assert final_instruments and len(final_instruments) > 0, "No instruments found"
        primary_instrument = final_instruments[0]

        # 5. 构建回测配置
        self._backtest_config = BackTestConfig(
            instrument=primary_instrument,
            instruments=final_instruments,
            data_feeds=final_data_feeds,
            strategy=self._build_legacy_strategy_config(),
            start_date=self.START_DATE,
            end_date=self.END_DATE,
            initial_balances=self.INITIAL_BALANCES,
            logging=self._build_log_config(),
        )

        return self._backtest_config

    def _build_legacy_strategy_config(self) -> LegacyStrategyConfig:
        """构建兼容的策略配置"""
        strategy_cfg = self.strategy_config

        # 动态导入策略配置类
        params = self._build_strategy_params()

        return LegacyStrategyConfig(
            name=strategy_cfg.name,
            module_path=strategy_cfg.module_path,
            config_class=strategy_cfg.config_class,
            params=params,
        )

    def _build_strategy_params(self) -> Any:
        """构建策略参数对象"""
        strategy_cfg = self.strategy_config
        params_dict = deepcopy(strategy_cfg.parameters)

        # 应用覆盖配置
        if self.active_config.overrides:
            strategy_overrides = self.active_config.overrides.get("strategy", {})
            if strategy_overrides:
                params_dict.update(strategy_overrides)

        # 如果有配置类，尝试创建配置对象
        if strategy_cfg.config_class:
            try:
                # 动态导入配置类
                module_path = strategy_cfg.module_path
                config_class_name = strategy_cfg.config_class

                # 导入模块
                import importlib

                module = importlib.import_module(module_path)
                config_class = getattr(module, config_class_name)

                # 创建配置对象
                return config_class(**params_dict)

            except Exception as e:
                print(f"⚠️ Failed to create strategy config object: {e}")
                # 回退到字典
                return params_dict

        return params_dict

    def _build_log_config(self) -> LogConfig:
        """构建日志配置"""
        log_cfg = self.env_config.logging

        return LogConfig(
            log_level=log_cfg.level,
            log_level_file=log_cfg.file_level,
            log_component_levels=log_cfg.components,
            log_components_only=log_cfg.components_only,
        )

    # ==========================================
    # 配置管理功能
    # ==========================================

    def switch_environment(self, env_name: str):
        """
        切换环境配置

        Args:
            env_name: 环境名称
        """
        # 确保活跃配置已加载
        if self._active_config is None:
            raise ConfigValidationError(
                "Active config not loaded. Call reload() first."
            )

        # 更新活跃配置
        self._active_config.environment = env_name

        # 重新加载环境配置
        self._env_config = self.loader.load_environment_config(env_name)

        # 清除缓存
        self._backtest_config = None

    def switch_strategy(self, strategy_name: str):
        """
        切换策略配置

        Args:
            strategy_name: 策略名称
        """
        # 确保活跃配置已加载
        if self._active_config is None:
            raise ConfigValidationError(
                "Active config not loaded. Call reload() first."
            )

        # 更新活跃配置
        self._active_config.strategy = strategy_name

        # 重新加载策略配置
        self._strategy_config = self.loader.load_strategy_config(strategy_name)

        # 清除缓存
        self._backtest_config = None

    def get_available_environments(self) -> List[str]:
        """获取可用的环境列表"""
        return self.paths.list_environments()

    def get_available_strategies(self) -> List[str]:
        """获取可用的策略列表"""
        return self.paths.list_strategies()

    def validate_all_configs(self) -> Dict[str, Any]:
        """验证所有配置文件"""
        return self.loader.validate_config_files()


# 全局配置管理器实例
_global_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager()
    return _global_config_manager


def reload_global_config():
    """重新加载全局配置"""
    global _global_config_manager
    if _global_config_manager is not None:
        _global_config_manager.reload()


# 导出主要类和函数
__all__ = [
    "ConfigManager",
    "get_config_manager",
    "reload_global_config",
]
