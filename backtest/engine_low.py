import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from nautilus_trader.analysis.tearsheet import create_tearsheet
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models.fee import MakerTakerFeeModel
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import RiskEngineConfig
from nautilus_trader.model import BarType, TraderId
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.enums import (
    AccountType,
    BarAggregation,
    BookType,
    OmsType,
)
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.persistence.wranglers import BarDataWrangler

from backtest.utils import (
    filter_strategy_params,
    load_strategy_class,
    load_strategy_config_class,
    resolve_instrument_path,
)
from config.definitions import BackTestConfig, DataConfig
from utils.instrument_loader import load_instrument


def _load_data_for_inst(
    engine: BacktestEngine,
    base_dir: Path,
    cfg: BackTestConfig,
    inst,
    data_cfg: DataConfig,
) -> Optional[BarType]:
    """
    加载 CSV 数据并注入回测引擎。

    Args:
        engine: Nautilus 回测引擎实例
        base_dir: 项目根目录
        cfg: 回测全局配置
        inst: Instrument 实例
        data_cfg: 数据配置项

    Returns:
        Optional[BarType]: 成功加载则返回对应的 BarType，否则返回 None
    """
    feed_bar_type_str = f"{inst.id}-{data_cfg.bar_type_str}"
    feed_bar_type = BarType.from_str(feed_bar_type_str)

    csv_path = base_dir / "data" / "raw" / data_cfg.csv_file_name

    if not csv_path.exists():
        print(f"⚠️ Data file not found: {csv_path}")
        return None

    try:
        # 加载并预处理数据
        df = pd.read_csv(csv_path)

        # 统一处理时间列
        if "timestamp" in df.columns:
            df["timestamp"] = (
                pd.to_datetime(df["timestamp"], unit="ms")
                if df["timestamp"].dtype != "datetime64[ns]"
                else df["timestamp"]
            )
            df.set_index("timestamp", inplace=True)
        elif "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)

        # 仅保留核心 OHLCV 列
        df = df[["open", "high", "low", "close", "volume"]]

        # 按需截取时间段
        if cfg.start_date:
            df = df[df.index >= pd.Timestamp(cfg.start_date)]
        if cfg.end_date:
            df = df[df.index <= pd.Timestamp(cfg.end_date)]

        if len(df) == 0:
            print(f"⚠️ No data available for {inst.id} in the specified range.")
            return None

        # 使用 Wrangler 将 DataFrame 转换为 Nautilus 内部 Bar 格式
        wrangler = BarDataWrangler(feed_bar_type, inst)
        bars = wrangler.process(df)
        engine.add_data(bars)

        return feed_bar_type
    except Exception as e:
        print(f"❌ Error loading data for {inst.id}: {e}")
        return None


def run_low_level(cfg: BackTestConfig, base_dir: Path):
    """
    运行低级引擎回测 (Low-level Engine)。
    低级引擎直接操作内存中的数据对象，适合灵活的单机回测。
    """
    print(f"🚀 Starting Multi-Instrument Low-Level Backtest: {cfg.strategy.name}")

    # 1. 配置日志
    logging_config = None
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_colors=cfg.logging.log_colors,
            use_pyo3=cfg.logging.use_pyo3,
            log_component_levels=cfg.logging.log_component_levels,
            log_components_only=bool(cfg.logging.log_components_only),
            log_directory=str(base_dir / "log" / "backtest" / "low_level"),
        )

    # 2. 初始化引擎
    engine_config = BacktestEngineConfig(
        trader_id=TraderId("BACKTESTER-001"),
        logging=logging_config,
        risk_engine=RiskEngineConfig(bypass=False),
    )
    engine = BacktestEngine(engine_config)

    # 3. 配置交易所 (Venue)
    engine.add_venue(
        venue=Venue(cfg.instrument.venue_name),
        oms_type=OmsType.HEDGING,
        book_type=BookType.L1_MBP,
        account_type=AccountType.MARGIN,
        base_currency=USDT,
        starting_balances=cfg.initial_balances,
        trade_execution=True,
        fee_model=MakerTakerFeeModel(),
    )

    # 4. 加载 Universe 定义
    universe_symbols = set()
    u_name = None
    params = cfg.strategy.params

    # 尝试从参数中获取 universe 文件名
    if isinstance(params, dict):
        u_name = params.get("universe_filename")
    elif hasattr(params, "universe_filename"):
        u_name = getattr(params, "universe_filename")

    if u_name:
        universe_file = base_dir / "data" / u_name
        if universe_file.exists():
            with open(universe_file, "r") as f:
                u_data = json.load(f)
                for month_list in u_data.values():
                    universe_symbols.update(month_list)
            print(f"🌌 Universe loaded: {len(universe_symbols)} symbols found.")

    # 5. 加载策略与配置类
    StrategyClass = load_strategy_class(cfg.strategy.module_path, cfg.strategy.name)
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    loaded_instruments = {}
    strategies_count = 0

    if universe_symbols:
        # === Case A: Universe 多标的模式 (如 RS-Squeeze) ===
        print(
            f"🌌 Running in Universe Mode with {len(universe_symbols)} potential symbols."
        )

        # 5.1 加载基准数据 (Benchmark)
        benchmark_bt = None
        for feed in cfg.data_feeds:
            if feed.label == "benchmark" and feed.instrument_id:
                symbol_part = feed.instrument_id.split(".")[0]
                venue_part = (
                    feed.instrument_id.split(".")[1]
                    if "." in feed.instrument_id
                    else cfg.instrument.venue_name
                )
                path = resolve_instrument_path(base_dir, venue_part, symbol_part)
                if path.exists():
                    benchmark_inst = load_instrument(path)
                    engine.add_instrument(benchmark_inst)
                    loaded_instruments[str(benchmark_inst.id)] = benchmark_inst
                    benchmark_bt = _load_data_for_inst(
                        engine, base_dir, cfg, benchmark_inst, feed
                    )

        # 5.2 获取主数据模板 (用于推断 Universe 成员的数据路径)
        main_feed_template = next(
            (f for f in cfg.data_feeds if f.label == "main"), None
        )
        if not main_feed_template:
            print(
                "❌ No 'main' data feed found in config to use as template for universe."
            )
            return

        for symbol in sorted(list(universe_symbols)):
            # 转换符号格式 (e.g., SOLUSDT:USDT -> SOL-USDT-SWAP)
            raw_pair = symbol.split(":")[0]
            clean_base = raw_pair.replace("USDT", "")
            inst_id_str = f"{clean_base}-USDT-SWAP.{cfg.instrument.venue_name}"

            if inst_id_str in loaded_instruments:
                inst = loaded_instruments[inst_id_str]
            else:
                inst_path = resolve_instrument_path(
                    base_dir, cfg.instrument.venue_name, inst_id_str.split(".")[0]
                )
                if not inst_path.exists():
                    continue
                try:
                    inst = load_instrument(inst_path)
                    engine.add_instrument(inst)
                    loaded_instruments[str(inst.id)] = inst
                except Exception as e:
                    print(f"⚠️ Failed to load instrument {inst_id_str}: {e}")
                    continue

            try:
                # 构造 Universe 成员的数据路径
                timeframe = f"{main_feed_template.bar_period}"
                if main_feed_template.bar_aggregation == BarAggregation.HOUR:
                    timeframe += "h"
                elif main_feed_template.bar_aggregation == BarAggregation.DAY:
                    timeframe += "d"
                else:
                    timeframe += "m"

                universe_data_cfg = DataConfig(
                    csv_file_name=f"{clean_base}USDT/{cfg.instrument.venue_name.lower()}-{clean_base}USDT-{timeframe}-{cfg.start_date}_{cfg.end_date}.csv",
                    label="main",
                )

                bt = _load_data_for_inst(engine, base_dir, cfg, inst, universe_data_cfg)
                if bt:
                    feed_bar_types = {"main": str(bt)}
                    if benchmark_bt:
                        feed_bar_types["benchmark"] = str(benchmark_bt)

                    # 解析策略参数
                    strat_params = cfg.strategy.resolve_params(
                        instrument_id=inst.id,
                        leverage=cfg.instrument.leverage,
                        feed_bar_types=feed_bar_types,
                    )

                    if u_name:
                        strat_params["universe_filename"] = u_name

                    # 实例化策略
                    final_params = filter_strategy_params(strat_params, ConfigClass)
                    strat_config = ConfigClass(**final_params)
                    strategy = StrategyClass(config=strat_config)
                    engine.add_strategy(strategy)
                    strategies_count += 1
            except Exception as e:
                print(f"⚠️ Failed to setup {inst_id_str}: {e}")

    else:
        # === Case B: 单标的模式 (如 Dual Thrust) ===
        print(f"🎯 Running in Single-Instrument Mode: {cfg.instrument.instrument_id}")

        # 5.1 加载主标的
        symbol_part = cfg.instrument.instrument_id.split(".")[0]
        venue_part = cfg.instrument.venue_name
        inst_path = resolve_instrument_path(base_dir, venue_part, symbol_part)
        if not inst_path.exists():
            print(f"❌ Main instrument file not found: {inst_path}")
            return

        main_inst = load_instrument(inst_path)
        engine.add_instrument(main_inst)
        loaded_instruments[str(main_inst.id)] = main_inst

        # 5.2 加载所有配置的数据流 (Main + Aux)
        feed_bar_types = {}
        for feed in cfg.data_feeds:
            target_inst = main_inst
            if feed.instrument_id and feed.instrument_id != str(main_inst.id):
                s_part = feed.instrument_id.split(".")[0]
                v_part = (
                    feed.instrument_id.split(".")[1]
                    if "." in feed.instrument_id
                    else venue_part
                )
                aux_path = resolve_instrument_path(base_dir, v_part, s_part)
                if aux_path.exists():
                    target_inst = load_instrument(aux_path)
                    if str(target_inst.id) not in loaded_instruments:
                        engine.add_instrument(target_inst)
                        loaded_instruments[str(target_inst.id)] = target_inst

            bt = _load_data_for_inst(engine, base_dir, cfg, target_inst, feed)
            if bt:
                feed_bar_types[feed.label] = str(bt)

        # 5.3 实例化策略
        strat_params = cfg.strategy.resolve_params(
            instrument_id=main_inst.id,
            leverage=cfg.instrument.leverage,
            feed_bar_types=feed_bar_types,
        )
        final_params = filter_strategy_params(strat_params, ConfigClass)
        strat_config = ConfigClass(**final_params)
        strategy = StrategyClass(config=strat_config)
        engine.add_strategy(strategy)
        strategies_count = 1

    # 6. 执行回测
    if strategies_count == 0:
        print("❌ No strategies were initialized. Check your universe and data files.")
        engine.dispose()
        return

    print(f"⏳ Running engine with {strategies_count} strategy instances...")
    engine.run()
    print("✅ Backtest finished.")

    # 7. 生成报告
    if cfg.output_html_report:
        output_dir = base_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = output_dir / f"low_backtest_{cfg.strategy.name}_{timestamp}.html"
        create_tearsheet(engine=engine, output_path=str(report_path))
        print(f"📊 Report generated: {report_path}")

    # 8. 清理
    engine.reset()
    engine.dispose()
