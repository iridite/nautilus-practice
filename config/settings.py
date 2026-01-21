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
from strategy.oi_divergence import OIDivergenceConfig
from strategy.oi_divergence_strategy import (
    OIDivergenceStrategy,
    OIDivergenceStrategyConfig,
)
from strategy.rs_squeeze import RSSqueezeConfig

# ==========================================
# 1. 基础回测环境 (Global Environment)
# ==========================================
VENUE = "BINANCE"
INSTRUMENT_TYPE = InstrumentType.SWAP
# 🔥 OI 数据限制：Binance 仅提供最近 30 天的 OI 历史数据
# 当前可用数据范围：2025-12-31 至 2026-01-21 (约 21 天)
START_DATE = "2025-12-31"
END_DATE = "2026-01-21"
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


def create_instrument_cfg(symbol: str) -> InstrumentConfig:
    """
    根据符号创建 InstrumentConfig。
    支持格式: "SOLUSDT", "SOLUSDT:USDT", "SOL"
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
        venue_name=VENUE,
        quote_currency=quote_currency,
        base_currency=base_currency,
        type=INSTRUMENT_TYPE,
    )


def load_universe_symbols(universe_file: str) -> set:
    """
    从 Universe 文件加载所有符号。

    Args:
        universe_file: Universe 文件路径 (可以是绝对路径或相对于 data 目录的路径)

    Returns:
        set: 所有唯一符号的集合
    """
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
    params=RSSqueezeConfig(),
)

# 策略 C: OI Divergence 持仓量背离策略 (风控增强版 v3.0)
OI_DIVERGENCE_STRATEGY_V3 = StrategyConfig(
    name="OIDivergenceStrategy",
    module_path="strategy.oi_divergence_strategy",
    config_class="OIDivergenceStrategyConfig",  # 🔥 明确指定配置类名
    params=OIDivergenceStrategyConfig(
        # 数据设定
        instrument_id="",  # 由系统自动填充
        bar_type="",  # 由系统自动填充
        # Research 参数 (策略核心逻辑)
        lookback_bars=48,  # 48小时回溯期计算支撑/阻力
        oi_lookback=12,  # OI移动平均周期12小时
        oi_decline_threshold=0.05,  # OI下降5%触发背离信号
        funding_rate_threshold_annual=30.0,  # 年化资金费率30%以上表示极度拥挤
        use_funding_filter=True,  # 启用资金费率过滤
        breakout_reentry_pct=0.002,  # 回撤0.2%进入
        # 出场参数
        tp_use_vwap=True,  # 止盈目标使用VWAP
        vwap_period=48,  # VWAP周期48小时
        time_stop_bars=24,  # 时间止损24小时
        # 🔥 Risk Enhancement: ATR动态止损
        use_atr_stop=True,  # 启用ATR动态止损
        atr_period=14,  # ATR计算周期
        atr_stop_multiplier=2.0,  # ATR止损倍数 (2× ATR)
        stop_loss_pct=0.01,  # 固定止损1% (ATR未初始化时的后备)
        # 🔥 Risk Enhancement: ATR动态仓位管理
        use_atr_position_sizing=True,  # 启用ATR动态仓位
        max_position_risk_pct=0.1,  # 单笔最大风险10%账户权益
        # 🔥 Risk Enhancement: 滑点控制
        max_slippage_pct=0.005,  # 最大允许滑点0.5%
        enable_slippage_alert=True,  # 启用滑点告警
        # 仓位控制
        max_positions=1,  # 最大持仓数
        qty_percent=Decimal("0.1"),  # 默认仓位10% (ATR仓位未启用时使用)
        leverage=1,  # 默认杠杆倍数
        # 日志控制
        enable_signal_logging=True,  # 启用详细信号日志
        enable_quality_check=True,  # 启用数据质量检查
    ),
)

# 策略 C (旧版): OI Divergence 持仓量背离策略 (保留供旧脚本使用)
OI_DIVERGENCE_STRATEGY = StrategyConfig(
    name="OIDivergenceStrategy",
    module_path="strategy.oi_divergence",
    params=OIDivergenceConfig(
        lookback_bars=48,  # 48小时回溯期计算支撑/阻力
        oi_decline_threshold=0.05,  # OI下降5%触发背离信号
        funding_rate_threshold_annual=30.0,  # 年化资金费率30%以上表示极度拥挤
        use_funding_filter=True,  # 启用资金费率过滤
        breakout_reentry_pct=0.002,  # 回撤0.2%进入
        tp_use_vwap=True,  # 止盈目标使用VWAP
        vwap_period=48,  # VWAP周期48小时
        stop_loss_pct=0.01,  # 硬止损1%
        time_stop_bars=24,  # 时间止损24小时
        max_positions=1,  # 最大持仓数
    ),
)

# ==========================================
# 4. 运行选择 (Active Configuration)
# ==========================================

# 🔥 切换到 OI Divergence Strategy v3.0 (Risk-Enhanced)
ACTIVE_STRATEGY = OI_DIVERGENCE_STRATEGY_V3
# 默认主标的 (当不是 Universe 模式时使用)
PRIMARY_SYMBOL = "BTCUSDT"

# ==========================================
# 5. 自动化构建 BackTestConfig
# ==========================================


def build_config() -> BackTestConfig:
    # 1. 初始化列表
    final_instruments = []
    final_data_feeds = []

    # 2. 检查策略是否带有 Universe
    params = ACTIVE_STRATEGY.params
    universe_file = None
    if isinstance(params, dict):
        universe_file = params.get("universe_filename") or params.get(
            "universe_filepath"
        )
    else:
        universe_file = getattr(params, "universe_filename", None) or getattr(
            params, "universe_filepath", None
        )

    if universe_file:
        # --- 多标的模式 ---
        print(f"🌐 Building Multi-Asset Config from {universe_file}...")

        # 加载 Universe 中的所有符号
        universe_symbols = load_universe_symbols(universe_file)

        if universe_symbols:
            print(f"🌌 Universe loaded: {len(universe_symbols)} unique symbols found.")

            # 为每个符号创建 InstrumentConfig 和 DataConfig
            for symbol in sorted(universe_symbols):
                raw_symbol = symbol.split(":")[0]  # SOLUSDT:USDT -> SOLUSDT

                # 创建 InstrumentConfig
                inst_cfg = create_instrument_cfg(symbol)
                final_instruments.append(inst_cfg)

                # 创建主数据流 (main)
                data_cfg = create_data_cfg(raw_symbol, MAIN_TIMEFRAME, "main")
                # 绑定 instrument_id 到 data_cfg
                data_cfg.instrument_id = inst_cfg.instrument_id
                final_data_feeds.append(data_cfg)

                # 可选：为每个标的创建趋势数据流 (trend)
                # 注意：这会大幅增加数据量，如果不需要可以注释掉
                # trend_cfg = create_data_cfg(raw_symbol, TREND_TIMEFRAME, "trend")
                # trend_cfg.instrument_id = inst_cfg.instrument_id
                # final_data_feeds.append(trend_cfg)
        else:
            print("⚠️ No symbols found in universe, falling back to single-asset mode.")
            # 回退到单标的模式
            inst = InstrumentConfig(
                venue_name=VENUE,
                quote_currency=PRIMARY_SYMBOL.replace("USDT", ""),
                base_currency="USDT",
                type=INSTRUMENT_TYPE,
            )
            final_instruments.append(inst)
            final_data_feeds.append(
                create_data_cfg(PRIMARY_SYMBOL, MAIN_TIMEFRAME, "main")
            )
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
        main_cfg = create_data_cfg(PRIMARY_SYMBOL, MAIN_TIMEFRAME, "main")
        main_cfg.instrument_id = inst.instrument_id
        final_data_feeds.append(main_cfg)

        trend_cfg = create_data_cfg(PRIMARY_SYMBOL, TREND_TIMEFRAME, "trend")
        trend_cfg.instrument_id = inst.instrument_id
        final_data_feeds.append(trend_cfg)

    # 3. 无论什么策略，通常都需要一个 Benchmark (如 BTC)
    # 检查 BTC 是否已经在列表中
    btc_exists = any(inst.quote_currency == "BTC" for inst in final_instruments)
    if not btc_exists:
        btc_inst = InstrumentConfig(
            venue_name=VENUE,
            quote_currency="BTC",
            base_currency="USDT",
            type=INSTRUMENT_TYPE,
        )
        final_instruments.append(btc_inst)

    # 添加 benchmark 数据流 (1h 用于 RS 计算)
    benchmark_cfg = create_data_cfg("BTCUSDT", MAIN_TIMEFRAME, "benchmark")
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
        benchmark_trend_cfg = create_data_cfg(
            "BTCUSDT", TREND_TIMEFRAME, "benchmark_trend"
        )
        benchmark_trend_cfg.instrument_id = btc_instrument_id
        final_data_feeds.append(benchmark_trend_cfg)

    # 4. 选择主标的 (用于兼容单标的模式的旧代码)
    # 在多标的模式下，选择第一个作为"主标的"用于兼容性

    assert final_instruments and len(final_instruments) > 0, "No instruments found"
    primary_instrument = final_instruments[0]

    return BackTestConfig(
        instrument=primary_instrument,
        instruments=final_instruments,
        data_feeds=final_data_feeds,
        strategy=ACTIVE_STRATEGY,
        start_date=START_DATE,
        end_date=END_DATE,
        initial_balances=INITIAL_BALANCES,
        logging=LogConfig(
            log_level="INFO",  # 回测时使用 WARNING 级别减少日志 I/O
            log_level_file="DEBUG",  # 文件日志也改为 WARNING 加速回测
            log_component_levels={
                "BacktestEngine": "INFO",
                "DataFeed": "INFO",
                "RSSqueezeStrategy": "INFO",
            },
            log_components_only=True,
        ),
    )


# 导出给 main.py 使用
current_config = build_config()
