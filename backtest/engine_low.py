import gc
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from nautilus_trader.analysis.tearsheet import create_tearsheet
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models.fee import MakerTakerFeeModel
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import RiskEngineConfig
from nautilus_trader.model import BarType, TraderId
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import (
    AccountType,
    BookType,
    OmsType,
)
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.wranglers import BarDataWrangler
from pandas import DataFrame

from backtest.exceptions import (
    BacktestEngineError,
    CustomDataError,
    DataLoadError,
    InstrumentLoadError,
    ValidationError,
)
from backtest.utils import (
    filter_strategy_params,
    load_strategy_class,
    load_strategy_config_class,
)
from config.definitions import (
    BackTestConfig,
    DataConfig,
)
from utils import load_ohlcv_csv
from utils.instrument_loader import load_instrument


def _load_data_for_feed(
    engine: BacktestEngine,
    base_dir: Path,
    cfg: BackTestConfig,
    data_cfg: DataConfig,
    loaded_instruments: Dict[str, Instrument],
) -> Optional[BarType]:
    """
    加载 CSV 数据并注入回测引擎 (Low-Level Engine 风格)

    Args:
        engine: BacktestEngine 实例
        base_dir: 项目基础目录
        cfg: 回测配置
        data_cfg: 数据配置
        loaded_instruments: 已加载的标的映射

    Returns:
        Optional[BarType]: 成功加载则返回 BarType，否则返回 None

    Raises:
        DataLoadError: 当数据加载失败时
    """
    # 确定关联的 Instrument ID
    inst_id_str = data_cfg.instrument_id or str(cfg.instrument.instrument_id)
    inst = loaded_instruments.get(inst_id_str)
    if not inst:
        raise DataLoadError(f"Instrument {inst_id_str} not found for feed {data_cfg.csv_file_name}")

    feed_bar_type_str = f"{inst.id}-{data_cfg.bar_type_str}"
    feed_bar_type = BarType.from_str(feed_bar_type_str)

    csv_path = data_cfg.full_path
    if not csv_path.exists():
        raise DataLoadError(f"CSV file not found: {csv_path}", str(csv_path))

    try:
        # 使用统一的数据加载器 (智能时间列检测 + 优化加载)
        df: DataFrame = load_ohlcv_csv(
            file_path=csv_path,
            start_date=cfg.start_date,
            end_date=cfg.end_date,
        )

        if len(df) == 0:
            raise DataLoadError(f"No data available in range for {data_cfg.csv_file_name}", str(csv_path))

        # 使用 Wrangler 转换并注入引擎
        wrangler = BarDataWrangler(feed_bar_type, inst)
        bars = wrangler.process(df)
        engine.add_data(bars)

        print(f"✅ Loaded {len(bars)} bars for {inst.id} ({data_cfg.label})")
        return feed_bar_type

    except Exception as e:
        if isinstance(e, DataLoadError):
            raise
        raise DataLoadError(f"Error loading {data_cfg.csv_file_name}: {e}", str(csv_path), e)


def _load_custom_data_to_engine(
    cfg: BackTestConfig,
    base_dir: Path,
    engine: BacktestEngine,
    loaded_instruments: Dict[str, Instrument],
) -> int:
    """
    加载自定义数据(OI, Funding Rate)到回测引擎 (Low-Level Engine 风格)

    Args:
        cfg: 回测配置
        base_dir: 项目基础目录
        engine: BacktestEngine 实例
        loaded_instruments: 已加载的标的映射

    Returns:
        int: 加载的数据点总数

    Raises:
        CustomDataError: 当自定义数据加载失败时
    """
    if not (cfg.start_date and cfg.end_date):
        print("⚠️ No date range specified, skipping custom data loading")
        return 0

    print("📊 Loading custom data (OI, Funding Rate)...")

    try:
        from utils.oi_funding_adapter import merge_custom_data_with_bars

        data_dir = base_dir / "data" / "raw"
        total_loaded = 0

        for inst_id_str, inst in loaded_instruments.items():
            instrument_id = inst.id
            symbol = str(instrument_id.symbol).split("-")[0]  # BTCUSDT-PERP -> BTCUSDT
            symbol_dir = data_dir / symbol

            if not symbol_dir.exists():
                continue

            # 查找数据文件
            oi_files = list(symbol_dir.glob("*-oi-1h-*.csv"))
            funding_files = list(symbol_dir.glob("*-funding-*.csv"))

            oi_data_list = []
            funding_data_list = []

            # 加载OI数据
            if oi_files:
                oi_data_list = _load_oi_data_from_files(oi_files, instrument_id)

            # 加载Funding Rate数据
            if funding_files:
                funding_data_list = _load_funding_data_from_files(funding_files, instrument_id)

            # 合并并添加到引擎
            if oi_data_list or funding_data_list:
                merged_data = merge_custom_data_with_bars(oi_data_list, funding_data_list)
                engine.add_data(merged_data)
                total_loaded += len(merged_data)
                print(f"   ✅ Added {len(merged_data)} custom data points for {symbol}")

        print(f"✅ Total custom data loaded: {total_loaded} points")
        return total_loaded

    except Exception as e:
        raise CustomDataError(f"Custom data loading failed: {e}", cause=e)


def _load_oi_data_from_files(oi_files: List[Path], instrument_id) -> List:
    """从文件加载OI数据 (简化版，适合Low-Level Engine)"""
    oi_data_list = []

    try:
        from decimal import Decimal

        import pandas as pd
        from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos

        from utils.custom_data import OpenInterestData

        for oi_file in oi_files:
            df = pd.read_csv(oi_file)
            df = df.sort_values("timestamp")  # 确保时间戳顺序

            prev_ts = 0
            for _, row in df.iterrows():
                ts_ms = int(row["timestamp"])

                # 验证时间戳单调递增
                if ts_ms < prev_ts:
                    print(f"⚠️ Warning: Non-monotonic timestamp in {oi_file.name}")
                prev_ts = ts_ms

                ts_event = millis_to_nanos(ts_ms)
                ts_init = ts_event

                oi_data = OpenInterestData(
                    instrument_id=instrument_id,
                    open_interest=Decimal(str(row["open_interest"])),
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                oi_data_list.append(oi_data)

    except Exception as e:
        print(f"❌ Error loading OI files: {e}")

    return oi_data_list


def _load_funding_data_from_files(funding_files: List[Path], instrument_id) -> List:
    """从文件加载Funding Rate数据 (简化版，适合Low-Level Engine)"""
    funding_data_list = []

    try:
        from decimal import Decimal

        import pandas as pd
        from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos

        from utils.custom_data import FundingRateData

        for funding_file in funding_files:
            df = pd.read_csv(funding_file)
            df = df.sort_values("timestamp")  # 确保时间戳顺序

            prev_ts = 0
            for _, row in df.iterrows():
                ts_ms = int(row["timestamp"])

                # 验证时间戳单调递增
                if ts_ms < prev_ts:
                    print(f"⚠️ Warning: Non-monotonic timestamp in {funding_file.name}")
                prev_ts = ts_ms

                ts_event = millis_to_nanos(ts_ms)
                ts_init = ts_event

                funding_data = FundingRateData(
                    instrument_id=instrument_id,
                    funding_rate=Decimal(str(row["funding_rate"])),
                    next_funding_time=None,
                    ts_event=ts_event,
                    ts_init=ts_init,
                )
                funding_data_list.append(funding_data)

    except Exception as e:
        print(f"❌ Error loading Funding files: {e}")

    return funding_data_list


def _process_backtest_results(
    cfg: BackTestConfig,
    base_dir: Path,
    engine: BacktestEngine,
) -> None:
    """
    处理回测结果 (Low-Level Engine 风格)

    Args:
        cfg: 回测配置
        base_dir: 项目基础目录
        engine: BacktestEngine 实例
    """
    try:
        # 简化的结果处理 - 只保存基本统计
        result_dict = {
            "meta": {
                "strategy_name": cfg.strategy.name,
                "timestamp": datetime.now().isoformat(),
                "engine_type": "low_level",
            },
            "summary": {
                "start_date": cfg.start_date,
                "end_date": cfg.end_date,
                "initial_balances": [str(balance) for balance in cfg.initial_balances],
            },
            "strategy_config": cfg.strategy.params if hasattr(cfg.strategy.params, "dict")
                               else cfg.strategy.params,
        }

        # 保存 JSON 结果
        result_dir = base_dir / "log" / "backtest" / "result"
        result_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"low_{cfg.strategy.name}_{timestamp}.json"
        filepath = result_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False, default=str)

        print(f"📁 Results saved to: {filepath}")

    except Exception as e:
        print(f"⚠️ Error saving results: {e}")


def run_low_level(cfg: BackTestConfig, base_dir: Path):
    """
    运行低级引擎回测 (Low-level Engine)

    保持 BacktestEngine 直接 API 的简洁特性，但增强错误处理和功能完整性。

    Args:
        cfg: 回测配置
        base_dir: 项目基础目录

    Raises:
        BacktestEngineError: 当回测执行失败时
        InstrumentLoadError: 当标的加载失败时
        DataLoadError: 当数据加载失败时
    """
    print(f"🚀 Starting Low-Level Backtest: {cfg.strategy.name}")

    try:
        # 1. 配置日志系统
        logging_config = None
        if cfg.logging:
            logging_config = LoggingConfig(
                log_level=cfg.logging.log_level,
                log_level_file=cfg.logging.log_level_file,
                log_directory=str(base_dir / "log" / "backtest" / "low_level"),
            )

        # 2. 初始化引擎
        engine = BacktestEngine(
            BacktestEngineConfig(
                trader_id=TraderId("BACKTESTER-001"),
                logging=logging_config,
                risk_engine=RiskEngineConfig(bypass=False),
            )
        )

        # 3. 配置交易所
        venue_name = cfg.instrument.venue_name if cfg.instrument else "BINANCE"
        engine.add_venue(
            venue=Venue(venue_name),
            oms_type=OmsType.NETTING,
            book_type=BookType.L1_MBP,
            account_type=AccountType.MARGIN,
            base_currency=USDT,
            starting_balances=cfg.initial_balances,
            trade_execution=True,
            fee_model=MakerTakerFeeModel(),
        )

        # 4. 加载标的定义
        loaded_instruments = {}
        total_feeds = len(cfg.data_feeds)

        for inst_cfg in cfg.instruments:
            inst_path = inst_cfg.get_json_path()
            if not inst_path.exists():
                raise InstrumentLoadError(f"Instrument path not found: {inst_path}", inst_cfg.instrument_id)

            try:
                inst = load_instrument(inst_path)
                engine.add_instrument(inst)
                loaded_instruments[str(inst.id)] = inst
                print(f"✅ Loaded instrument: {inst.id}")
            except Exception as e:
                raise InstrumentLoadError(f"Failed to load instrument {inst_cfg.instrument_id}: {e}",
                                        inst_cfg.instrument_id, e)

        # 5. 加载回测数据
        all_feeds = {}  # (instrument_id, label) -> bar_type_str
        for feed_idx, data_cfg in enumerate(cfg.data_feeds, 1):
            sys.stdout.write(f"\r📖 [{feed_idx}/{total_feeds}] Loading: {data_cfg.csv_file_name}")
            sys.stdout.flush()

            try:
                bt = _load_data_for_feed(engine, base_dir, cfg, data_cfg, loaded_instruments)
                if bt:
                    inst_id = data_cfg.instrument_id or str(cfg.instrument.instrument_id)
                    all_feeds[(inst_id, data_cfg.label)] = str(bt)
            except DataLoadError as e:
                print(f"\n❌ Failed to load {data_cfg.csv_file_name}: {e}")
                continue

        print(f"\n✅ Loaded {len(all_feeds)} data feeds")

        # 6. 加载自定义数据 (OI, Funding Rate)
        try:
            custom_data_count = _load_custom_data_to_engine(cfg, base_dir, engine, loaded_instruments)
        except CustomDataError as e:
            print(f"⚠️ Custom data loading failed: {e}")
            custom_data_count = 0

        # 7. 配置与添加策略
        StrategyClass = load_strategy_class(cfg.strategy.module_path, cfg.strategy.name)
        ConfigClass = load_strategy_config_class(
            cfg.strategy.module_path, cfg.strategy.resolve_config_class()
        )

        # 提取全局共享数据流
        global_feeds = {
            label: bt for (iid, label), bt in all_feeds.items() if label == "benchmark"
        }
        strategies_count = 0

        # 为每个拥有 'main' 数据的标的创建策略实例
        for inst_id, inst in loaded_instruments.items():
            local_feeds = {
                label: bt
                for (iid, label), bt in all_feeds.items()
                if iid == inst_id and label != "benchmark"
            }

            if "main" not in local_feeds:
                continue

            # 生成策略参数
            strat_params = cfg.strategy.resolve_params(
                instrument_id=inst.id,
                leverage=cfg.instrument.leverage if cfg.instrument else 1,
                feed_bar_types={**local_feeds, **global_feeds},
            )

            # 过滤参数并实例化策略
            final_params = filter_strategy_params(strat_params, ConfigClass)
            strat_config = ConfigClass(**final_params)
            engine.add_strategy(StrategyClass(config=strat_config))
            strategies_count += 1

        # 8. 执行回测
        if strategies_count == 0:
            raise BacktestEngineError("No strategy instances were created. Check config and data paths.")

        print(f"⏳ Running engine with {strategies_count} strategy instances...")
        engine.run()
        print("✅ Backtest Complete.")

        # 9. 处理结果
        _process_backtest_results(cfg, base_dir, engine)

        if cfg.output_html_report:
            output_dir = base_dir / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            report_path = (
                output_dir
                / f"low_{cfg.strategy.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )
            create_tearsheet(engine=engine, output_path=str(report_path))
            print(f"📊 HTML Report generated: {report_path}")

        # 10. 清理资源
        gc.collect()
        engine.reset()
        engine.dispose()
        print("🧹 Engine resources cleaned up")

    except (InstrumentLoadError, DataLoadError, CustomDataError) as e:
        print(f"❌ Backtest failed: {e}")
        raise
    except Exception as e:
        raise BacktestEngineError(f"Unexpected error during backtest: {e}", e)
