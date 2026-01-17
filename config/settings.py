import json
from decimal import Decimal
from pathlib import Path
from typing import List

from nautilus_trader.model import Money
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import BarAggregation, PriceType

from config.definitions import (
    BackTestConfig,
    DataConfig,
    InstrumentConfig,
    InstrumentType,
    LogConfig,
    StrategyConfig,
    project_root,
)
from strategy.dual_thrust import DualThrustConfig
from strategy.rs_squeeze import RSSqueezeConfig

# ==========================================
# 1. 基础回测环境 (Global Environment)
# ==========================================
VENUE = "BINANCE"
INSTRUMENT_TYPE = InstrumentType.SWAP
START_DATE = "2022-01-01"
END_DATE = "2026-01-14"
INITIAL_BALANCES = [Money("100", USDT)]

# 默认时间周期
MAIN_TIMEFRAME = "1h"
TREND_TIMEFRAME = "4h"


# ==========================================
# 2. 辅助工具：统一生成 DataConfig
# ==========================================
def create_data_cfg(symbol: str, timeframe: str, label: str = "main") -> DataConfig:
    """统一生成符合项目路径规范的 DataConfig"""
    # 只有在 universe 接管的时候，系统才能自动生成 DataConfig，故其他模式下需要自行配置
    # 格式：BTCUSDT/BINANCE-BTCUSDT-1h-2024-01-01_2024-12-31.csv
    safe_symbol = symbol.replace("/", "")
    filename = f"{VENUE.lower()}-{safe_symbol}-{timeframe}-{START_DATE}_{END_DATE}.csv"

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


# ==========================================
# 3. 策略库定义 (Strategy Library)
# ==========================================

# 策略 A: 单标的策略
DUAL_THRUST_STRATEGY = StrategyConfig(
    name="DualThrust",
    module_path="strategy.dual_thrust",
    params=DualThrustConfig(
        lookback_period=4,
        qty_percent=Decimal("0.1"),
    ),
)

# 策略 B: 多标的 Universe 策略
RS_SQUEEZE_STRATEGY = StrategyConfig(
    name="RSSqueezeStrategy",
    module_path="strategy.rs_squeeze",
    params=RSSqueezeConfig(
        rs_threshold=1.05,
        universe_filepath=str(
            project_root / "data" / "universe_test.json"
        ),  # 只需文件名，路径在 main.py 处理?
    ),
)

# ==========================================
# 4. 运行选择 (Active Configuration)
# ==========================================

# 在这里切换你想跑的策略
ACTIVE_STRATEGY = RS_SQUEEZE_STRATEGY
# 默认主标的 (当不是 Universe 模式时使用)
PRIMARY_SYMBOL = "SOLUSDT"

# ==========================================
# 5. 自动化构建 BackTestConfig
# ==========================================


def build_config() -> BackTestConfig:
    # 1. 初始化列表
    final_instruments = []
    final_data_feeds = []

    # 2. 检查策略是否带有 Universe
    params = ACTIVE_STRATEGY.params
    universe_file = (
        getattr(params, "universe_filename", None)
        if not isinstance(params, dict)
        else params.get("universe_filename")
    )

    if universe_file:
        # --- 多标的模式 ---
        print(f"🌐 Building Multi-Asset Config from {universe_file}...")
        # 注意：这里的 Instrument 加载在 main.py 里会根据 Universe 文件进一步补全
        # 这里我们至少放一个主标的作为种子，或者留空让 main.py 填充
        pass
    else:
        # --- 单标的模式 ---
        print(f"🎯 Building Single-Asset Config for {PRIMARY_SYMBOL}...")
        inst = InstrumentConfig(
            venue_name=VENUE,
            quote_currency=PRIMARY_SYMBOL.replace("USDT", ""),
            base_currency="USDT",
            type=INSTRUMENT_TYPE,
        )
        final_instruments.append(inst)
        # 添加数据流
        final_data_feeds.append(create_data_cfg(PRIMARY_SYMBOL, MAIN_TIMEFRAME, "main"))
        final_data_feeds.append(
            create_data_cfg(PRIMARY_SYMBOL, TREND_TIMEFRAME, "trend")
        )

    # 3. 无论什么策略，通常都需要一个 Benchmark (如 BTC)?
    final_data_feeds.append(create_data_cfg("BTCUSDT", MAIN_TIMEFRAME, "benchmark"))

    return BackTestConfig(
        instrument=final_instruments[0] if final_instruments else None,  # type: ignore
        instruments=final_instruments,
        data_feeds=final_data_feeds,
        strategy=ACTIVE_STRATEGY,
        start_date=START_DATE,
        end_date=END_DATE,
        initial_balances=INITIAL_BALANCES,
        logging=LogConfig(
            log_component_levels={
                "BacktestEngine": "INFO",
                "DataFeed": "DEBUG",
                "RSSqueezeStrategy": "INFO",
            }
        ),
    )


# 导出给 main.py 使用
current_config = build_config()
