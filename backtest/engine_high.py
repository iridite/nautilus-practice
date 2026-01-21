import gc
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from nautilus_trader.backtest.config import (
    BacktestDataConfig,
    BacktestRunConfig,
    BacktestVenueConfig,
    ImportableFeeModelConfig,
)
from nautilus_trader.backtest.node import (
    BacktestEngineConfig,
    BacktestNode,
)
from nautilus_trader.backtest.results import BacktestResult
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import ImportableStrategyConfig, RiskEngineConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.persistence.loaders import CSVBarDataLoader
from nautilus_trader.persistence.wranglers import BarDataWrangler
from pandas import DataFrame

from backtest.utils import (
    filter_strategy_params,
    load_strategy_config_class,
)
from config.definitions import BackTestConfig
from utils.instrument_loader import load_instrument


def run_high_level(cfg: BackTestConfig, base_dir: Path):
    """
    运行高级引擎回测 (High-level Engine/BacktestNode)。
    完全由 BackTestConfig 驱动，移除了硬编码的 Universe 加载逻辑。
    """
    print(f"🚀 Starting High-Level Backtest: {cfg.strategy.name}")

    data_path: Path = base_dir / "data"
    catalog_path: Path = data_path / "parquet" / f"{cfg.strategy.name}"

    # 1. 准备策略与配置类（用于参数过滤）
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    strategies = []
    loaded_instruments = {}

    # 用于合并同一 instrument_id 的多个 bar_types
    # 结构: {instrument_id: {"bar_types": [str], "catalog_path": str}}
    data_config_by_inst = {}

    # 预分组：将数据流按 InstrumentID 归类，提升大规模 Universe 下的性能
    feeds_by_inst = defaultdict(dict)
    global_feeds = {}

    # 创建 instrument_id -> inst_cfg 的映射用于快速查找
    inst_cfg_map = {ic.instrument_id: ic for ic in cfg.instruments}

    _catalog = ParquetDataCatalog(catalog_path)

    # 2. 数据处理与标的加载 (合并原有循环，减少冗余遍历)
    total_feeds = len(cfg.data_feeds)
    for feed_idx, data_cfg in enumerate(cfg.data_feeds, 1):
        # 优先使用 data_cfg 中的 instrument_id，如果为 None 则回退到主标的配置
        inst_id = data_cfg.instrument_id
        if inst_id is None and cfg.instrument is not None:
            inst_id = cfg.instrument.instrument_id

        # 2.1 按需加载标的信息 (仅加载有数据流定义的标的)
        if inst_id is not None and inst_id not in loaded_instruments:
            inst_cfg = inst_cfg_map.get(inst_id)
            if inst_cfg:
                inst_path = inst_cfg.get_json_path()
                if inst_path.exists():
                    try:
                        loaded_instruments[inst_id] = load_instrument(inst_path)
                    except Exception as e:
                        print(f"⚠️ Failed to load instrument {inst_id}: {e}")
                        continue
                else:
                    print(f"⚠️ Instrument path not found: {inst_path}")
                    continue
            else:
                print(f"⚠️ No instrument configuration found for {inst_id}")
                continue

        inst = loaded_instruments[inst_id]
        csv_path = data_cfg.full_path
        assert csv_path.exists(), f"CSV file not found: {csv_path}"

        feed_bar_type_str = f"{inst.id}-{data_cfg.bar_type_str}"

        # 2.2 归类数据流标签 (benchmark 为全局，其余归属特定标的)
        if data_cfg.label == "benchmark":
            global_feeds[data_cfg.label] = feed_bar_type_str
        else:
            feeds_by_inst[inst_id][data_cfg.label] = feed_bar_type_str

        # 2.3 高级引擎需要将数据导入 Catalog (Parquet)
        # 优化：先检查 catalog 中是否已存在该 bar_type 的数据，避免重复导入
        bar_type = BarType.from_str(feed_bar_type_str)
        existing_intervals = _catalog.get_intervals(
            data_cls=Bar, identifier=str(bar_type)
        )

        if existing_intervals:
            # 单行更新进度
            sys.stdout.write(
                f"\r⏩ [{feed_idx}/{total_feeds}] Skipping: {bar_type.instrument_id} (exists in catalog){' ' * 20}"
            )
            sys.stdout.flush()
        else:
            try:
                sys.stdout.write(
                    f"\r📖 [{feed_idx}/{total_feeds}] Importing: {bar_type.instrument_id}{' ' * 30}"
                )
                sys.stdout.flush()
                catalog_loader(
                    catalog=_catalog,
                    csv_path=csv_path,
                    instrument=inst,
                    bar_type=bar_type,
                )
            except Exception as e:
                print(
                    f"\n[Backtest Engine High] ❌ Error loading {data_cfg.csv_file_name}: {e}"
                )

        # 2.4 合并同一 instrument_id 的 bar_types
        # 关键：必须使用 bar_types (list[str]) 而非 bar_type，否则参数被忽略导致无数据加载！
        inst_id_str = str(inst.id)
        if inst_id_str not in data_config_by_inst:
            data_config_by_inst[inst_id_str] = {
                "instrument_id": inst.id,
                "bar_types": [],
                "catalog_path": str(catalog_path),
            }
        # 避免添加重复的 bar_type
        bar_type_str = str(bar_type)
        if bar_type_str not in data_config_by_inst[inst_id_str]["bar_types"]:
            data_config_by_inst[inst_id_str]["bar_types"].append(bar_type_str)

    # 注意：自定义数据（OI, Funding）稍后通过 engine.add_data() 直接添加

    # 4. 循环生成策略配置
    strategy_path = f"{cfg.strategy.module_path}:{cfg.strategy.name}"
    config_path = f"{cfg.strategy.module_path}:{cfg.strategy.resolve_config_class()}"

    for inst_id, inst in loaded_instruments.items():
        local_feeds = feeds_by_inst.get(inst_id, {})

        # 核心逻辑：只有拥有 'main' 数据流的标的才实例化策略
        if "main" not in local_feeds:
            continue

        # 合并本地和全局数据流标签
        combined_feeds = {**local_feeds, **global_feeds}

        # 生成并过滤参数
        # 注意：resolve_params 内部会自动处理 cfg.strategy.params 中的原始参数
        strat_params = cfg.strategy.resolve_params(
            instrument_id=inst.id,
            leverage=cfg.instrument.leverage if cfg.instrument else 1,
            # TODO：所以说杠杆不能跟 inst 绑定
            feed_bar_types=combined_feeds,
        )

        final_params = filter_strategy_params(strat_params, ConfigClass)

        # 封装为 Nautilus 可识别的导入配置
        strategies.append(
            ImportableStrategyConfig(
                strategy_path=strategy_path,
                config_path=config_path,
                config=final_params,
            )
        )

    # 3. 从合并后的配置生成 BacktestDataConfig 列表
    backtest_data_configs = []
    for inst_id_str, cfg_data in data_config_by_inst.items():
        backtest_data_configs.append(
            BacktestDataConfig(
                catalog_path=cfg_data["catalog_path"],
                data_cls="nautilus_trader.model.data:Bar",
                instrument_id=cfg_data["instrument_id"],
                bar_types=cfg_data["bar_types"],  # 合并后的 bar_types 列表
                start_time=cfg.start_date,
                end_time=cfg.end_date,
            )
        )

    # 注意：自定义数据（OI, Funding Rate）将通过 engine.add_data() 直接添加
    # 而不是通过 BacktestDataConfig（因为不需要序列化到 Parquet）

    # 换行结束进度显示
    print(
        f"\n✅ Data import complete. Created {len(backtest_data_configs)} data configs (merged by instrument)."
    )

    # 诊断日志：单行刷新显示数据配置进度
    total_configs = len(backtest_data_configs)
    print(f"\n📋 BacktestDataConfig Summary: {total_configs} configs")
    for i, data_cfg in enumerate(backtest_data_configs, 1):
        sys.stdout.write(
            f"\r  Processing [{i}/{total_configs}]: {data_cfg.instrument_id}{'':20}"
        )
        sys.stdout.flush()
    print(f"\r  ✅ Loaded {total_configs} data configs{'':40}")

    # 验证 catalog 中实际存在的数据（单行刷新）
    print("🔍 Verifying catalog data availability...")
    verified_count = 0
    missing_count = 0
    total_bar_types = sum(
        len(data_cfg.bar_types or []) for data_cfg in backtest_data_configs
    )
    checked = 0
    for data_cfg in backtest_data_configs:
        if data_cfg.bar_types:
            for bt_str in data_cfg.bar_types:
                checked += 1
                intervals = _catalog.get_intervals(data_cls=Bar, identifier=bt_str)
                if intervals:
                    verified_count += 1
                else:
                    missing_count += 1
                    # 只打印缺失数据的警告
                    print(f"\n  ❌ {bt_str}: NO DATA FOUND IN CATALOG!")
                # 单行刷新进度
                sys.stdout.write(
                    f"\r  Verifying [{checked}/{total_bar_types}] ✅ {verified_count} | ❌ {missing_count}{'':20}"
                )
                sys.stdout.flush()
    print(
        f"\r  📊 Catalog verification: {verified_count} OK, {missing_count} missing{'':30}"
    )

    # 5. 配置交易所 (Venue)
    venue_name = (
        cfg.instrument.venue_name
        if cfg.instrument
        else cfg.data_feeds[0].csv_file_name.split("/")[-1].split("-")[0]
    )

    venue_configs = [
        BacktestVenueConfig(
            name=venue_name,
            oms_type="NETTING",
            account_type="MARGIN",
            base_currency="USDT",  # TODO：到时候使用内置的货币类型
            starting_balances=cfg.initial_balances,
            fee_model=ImportableFeeModelConfig(
                fee_model_path="nautilus_trader.backtest.models:MakerTakerFeeModel",
                config_path="nautilus_trader.backtest.config:MakerTakerFeeModelConfig",
                config={},
            ),
            trade_execution=True,
        ),
    ]

    # 6. 配置日志 (Logging)
    logging_config = None
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_component_levels=cfg.logging.log_component_levels,
            log_components_only=cfg.logging.log_components_only,
            log_directory=str(base_dir / "log" / "backtest" / "high_level"),
        )

    # 7. 执行回测 (Execution)
    if not strategies:
        print(
            "❌ No strategy instances were created. Please check your config and data paths."
        )
        return

    eng_cfg = BacktestEngineConfig(
        strategies=strategies,
        logging=logging_config,
        risk_engine=RiskEngineConfig(bypass=False),
    )

    assert len(backtest_data_configs) != 0, "No data feeds were configured."

    run_config = BacktestRunConfig(
        engine=eng_cfg,
        data=backtest_data_configs,
        venues=venue_configs,
        raise_exception=True,
    )

    gc.collect()
    node = BacktestNode(configs=[run_config])
    print(f"⏳ Running BacktestNode with {len(strategies)} strategy instances...")
    print(f"   - Data configs: {len(backtest_data_configs)}")
    print(f"   - Venue configs: {len(venue_configs)}")
    print(f"   - Strategy configs: {len(strategies)}")

    # === 🔥 加载自定义数据（OI 和 Funding Rate） ===
    # 在 node.run() 之前，先 build 引擎，然后直接添加自定义数据
    print(f"\n📊 Loading custom data (OI, Funding Rate)...")

    # 确保有日期范围
    if cfg.start_date and cfg.end_date:
        try:
            # 1. Build the engine
            node.build()

            # 2. Get the underlying engine
            engine = node.get_engine(run_config.id)

            if engine is None:
                print(f"   ⚠️  Could not get engine from node")
            else:
                # 3. Load and add custom data直接从文件
                from utils.oi_funding_adapter import (
                    OIFundingDataLoader,
                    merge_custom_data_with_bars,
                )

                data_dir = base_dir / "data" / "raw"

                for inst_id_str, inst in loaded_instruments.items():
                    # inst_id_str 是字符串，inst 是 Instrument 对象
                    # 获取真正的 InstrumentId 对象
                    instrument_id = inst.id
                    symbol = str(instrument_id.symbol).split("-")[
                        0
                    ]  # BTCUSDT-PERP -> BTCUSDT
                    symbol_dir = data_dir / symbol

                    if not symbol_dir.exists():
                        print(f"   ⚠️  Data directory not found for {symbol}")
                        continue

                    # 使用 glob 查找文件（灵活匹配日期范围）
                    oi_files = list(symbol_dir.glob("*-oi-1h-*.csv"))
                    funding_files = list(symbol_dir.glob("*-funding-*.csv"))

                    oi_data_list = []
                    funding_data_list = []

                    # 加载 OI 数据
                    if oi_files:
                        from decimal import Decimal
                        from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos
                        from utils.custom_data import OpenInterestData
                        import pandas as pd

                        for oi_file in oi_files:
                            try:
                                df = pd.read_csv(oi_file)
                                for _, row in df.iterrows():
                                    ts_ms = int(row["timestamp"])
                                    ts_event = millis_to_nanos(ts_ms)
                                    ts_init = ts_event

                                    oi_data = OpenInterestData(
                                        instrument_id=instrument_id,  # 使用 InstrumentId 对象
                                        open_interest=Decimal(
                                            str(row["open_interest"])
                                        ),
                                        ts_event=ts_event,
                                        ts_init=ts_init,
                                    )
                                    oi_data_list.append(oi_data)
                            except Exception as e:
                                print(
                                    f"   ❌ Error loading OI file {oi_file.name}: {e}"
                                )

                    # 加载 Funding Rate 数据
                    if funding_files:
                        from decimal import Decimal
                        from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos
                        from utils.custom_data import FundingRateData
                        import pandas as pd

                        for funding_file in funding_files:
                            try:
                                df = pd.read_csv(funding_file)
                                for _, row in df.iterrows():
                                    ts_ms = int(row["timestamp"])
                                    ts_event = millis_to_nanos(ts_ms)
                                    ts_init = ts_event

                                    funding_data = FundingRateData(
                                        instrument_id=instrument_id,  # 使用 InstrumentId 对象
                                        funding_rate=Decimal(str(row["funding_rate"])),
                                        next_funding_time=None,
                                        ts_event=ts_event,
                                        ts_init=ts_init,
                                    )
                                    funding_data_list.append(funding_data)
                            except Exception as e:
                                print(
                                    f"   ❌ Error loading Funding file {funding_file.name}: {e}"
                                )

                    # Merge and add to engine
                    if oi_data_list or funding_data_list:
                        merged_data = merge_custom_data_with_bars(
                            oi_data_list, funding_data_list
                        )
                        engine.add_data(merged_data)
                        print(
                            f"   ✅ Added {len(merged_data)} custom data points for {symbol}"
                        )
                        print(f"      - OI: {len(oi_data_list)} points")
                        print(f"      - Funding: {len(funding_data_list)} points")
                    else:
                        print(f"   ⚠️  No custom data found for {symbol}")

        except Exception as e:
            import traceback

            print(f"   ⚠️  Custom data loading failed: {e}")
            traceback.print_exc()
            print(f"   Strategy will run without OI/Funding data")
    else:
        print(f"   ⚠️  No date range specified, skipping custom data loading")

    # Run the backtest
    results = node.run()

    print("✅ Backtest Complete.")

    # ===== 收集策略统计数据（用于保存到 JSON） =====
    # 注意：这些数据会被保存到 JSON 文件中供 AI 分析，但不会全部输出到终端
    filter_stats = None  # 信号过滤统计
    trade_metrics = None  # 交易明细列表
    try:
        from strategy.rs_squeeze import RSSqueezeStrategy

        # 获取统计数据（在终端打印之前先保存，避免打印后清空）
        filter_stats = RSSqueezeStrategy.get_filter_stats_summary()
        trade_metrics = RSSqueezeStrategy.get_trade_metrics()

        # 终端输出策略过滤器统计报告（详细格式化输出）
        RSSqueezeStrategy.print_filter_stats_report()

        # 重置类变量，避免多次回测时数据累积
        RSSqueezeStrategy.reset_class_stats()
    except ImportError:
        pass  # 非 RS Squeeze 策略时跳过
    except AttributeError:
        pass  # 策略没有相关方法时跳过

    # ===== 提取策略配置参数（完整保存到 JSON，不输出到终端） =====
    # 注意：cfg.strategy.params 可能是 dict 或 Pydantic 对象，需要统一转换
    strategy_params = cfg.strategy.params
    if hasattr(strategy_params, "model_dump"):
        # Pydantic v2 对象
        strategy_config = strategy_params.model_dump()
    elif hasattr(strategy_params, "dict"):
        # Pydantic v1 对象
        strategy_config = strategy_params.dict()
    elif isinstance(strategy_params, dict):
        strategy_config = strategy_params
    else:
        strategy_config = {}

    # ===== 构建回测配置信息（元数据） =====
    backtest_config = {
        "start_date": str(cfg.start_date),
        "end_date": str(cfg.end_date),
        "initial_balances": cfg.initial_balances,
        "instruments_count": len(loaded_instruments),
        "data_feeds_count": len(cfg.data_feeds),
        "strategies_count": len(strategies),
    }

    # ===== 终端输出 + JSON 保存 =====
    # 策略：终端只显示核心摘要（简洁），JSON 保存完整数据（供 AI 分析）
    if results:
        for result in results:
            # 终端输出（简化版，不包含策略配置）
            _print_results(
                result,
                strategy_config=None,  # 不传递配置到终端输出
            )

            # 构建完整结果字典（包含所有数据）
            result_dict = _build_result_dict(
                result=result,
                strategy_name=cfg.strategy.name,
                strategy_config=strategy_config,  # 完整配置保存到 JSON
                filter_stats=filter_stats,
                trade_metrics=trade_metrics,
                backtest_config=backtest_config,
            )

            # 保存为 JSON 文件
            json_path = _save_results_to_json(
                result_dict=result_dict,
                strategy_name=cfg.strategy.name,
                base_dir=base_dir,
            )
            # 提示用户 JSON 文件位置和包含的数据量
            print(f"📁 Complete results saved to: {json_path}")
            print(f"    ├─ Strategy parameters: {len(strategy_config)}")
            print(f"    ├─ Trade records: {len(trade_metrics) if trade_metrics else 0}")
            print(
                f"    └─ Filter stats: {len(filter_stats) if filter_stats else 0} instruments"
            )


def _build_result_dict(
    result: BacktestResult,
    strategy_name: str,
    strategy_config: Optional[Dict[str, Any]] = None,
    filter_stats: Optional[Dict[str, Dict[str, int]]] = None,
    trade_metrics: Optional[List[Dict]] = None,
    backtest_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    构建完整的回测结果字典，包含所有可用的回测数据。

    设计目标：
    1. 包含回测引擎能产生的所有数据，不遗漏任何信息
    2. 结构化组织，便于 AI 和人工分析
    3. 同时支持快速查看（performance）和深度分析（详细数据）

    JSON 结构：
    - meta: 元数据（策略名、时间戳、执行时长）
    - summary: 摘要统计（订单数、持仓数）
    - pnl: 盈亏数据（按货币分组）
    - returns: 收益率数据（夏普率、最大回撤、总回报等）
    - strategy_config: 完整的策略配置参数（供 AI 分析优化）
    - backtest_config: 回测配置信息（时间范围、标的数量等）
    - filter_stats: 信号过滤统计
        - by_instrument: 按标的分组的详细统计
        - total: 汇总统计
        - rates: 各种过滤率（通过率、各过滤器占比）
        - instrument_count: 标的数量
    - trade_metrics: 交易数据
        - trades: 所有交易的明细列表
        - analysis: 基础分析（胜率、盈亏比、均值等）
        - detailed_analysis: 详细分析（胜者 vs 败者对比）
    - performance: 性能摘要（整合关键指标，便于快速查看）

    Args:
        result: BacktestResult 对象
        strategy_name: 策略名称
        strategy_config: 策略配置参数（完整保存，供 AI 优化参考）
        filter_stats: 过滤器统计（来自策略类变量）
        trade_metrics: 交易指标（来自策略类变量）
        backtest_config: 回测配置信息

    Returns:
        完整的结果字典，包含回测引擎能输出的所有信息
    """
    result_dict = {
        "meta": {
            "strategy_name": strategy_name,
            "timestamp": datetime.now().isoformat(),
            "elapsed_time_seconds": result.elapsed_time,
        },
        "summary": {
            "total_orders": result.total_orders,
            "total_positions": result.total_positions,
        },
        "pnl": {},
        "returns": {},
        "strategy_config": strategy_config or {},
        "backtest_config": backtest_config or {},
        "filter_stats": {},
        "trade_metrics": {
            "trades": trade_metrics or [],
            "analysis": {},
            "detailed_analysis": {},  # 新增：更详细的交易分析
        },
        "performance": {},  # 新增：性能摘要
    }

    # 处理 PnL 指标
    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            result_dict["pnl"][str(currency)] = {
                k: v if v == v else None
                for k, v in metrics.items()  # NaN -> None
            }

    # 处理收益率指标
    if result.stats_returns:
        for currency, val in result.stats_returns.items():
            result_dict["returns"][str(currency)] = val if val == val else None

    # ===== 处理过滤器统计（完整保存所有过滤器细节） =====
    if filter_stats:
        # 汇总所有实例的统计
        total_stats = {}
        for inst_id, stats in filter_stats.items():
            for key, value in stats.items():
                total_stats[key] = total_stats.get(key, 0) + value

        # 计算过滤率
        signal_checks = total_stats.get("signal_checks", 0)
        all_passed = total_stats.get("all_passed", 0)

        filter_rates = {}
        if signal_checks > 0:
            filter_rates = {
                "pass_rate": (all_passed / signal_checks * 100)
                if signal_checks > 0
                else 0,
                "filter_rate": ((signal_checks - all_passed) / signal_checks * 100)
                if signal_checks > 0
                else 0,
            }
            # 计算各个过滤器的占比
            for key in [
                "fail_trend",
                "fail_squeeze",
                "fail_squeeze_maturity",
                "fail_rs",
                "fail_extension",
                "fail_btc_bear",
                "fail_breakout",
                "fail_volume",
            ]:
                if key in total_stats:
                    filter_rates[f"{key}_rate"] = total_stats[key] / signal_checks * 100

        result_dict["filter_stats"] = {
            "by_instrument": filter_stats,
            "total": total_stats,
            "rates": filter_rates,  # 新增：各种过滤率
            "instrument_count": len(filter_stats),
        }

    # ===== 处理交易指标分析（完整保存所有交易统计） =====
    if trade_metrics:
        winners = [t for t in trade_metrics if t.get("result") == "WINNER"]
        losers = [t for t in trade_metrics if t.get("result") == "LOSER"]

        # 基础统计
        analysis = {
            "total_trades": len(trade_metrics),
            "winning_trades": len(winners),
            "losing_trades": len(losers),
            "win_rate": len(winners) / len(trade_metrics) if trade_metrics else 0,
        }

        # 盈亏统计
        all_pnls = [t.get("pnl_pct", 0) for t in trade_metrics]
        analysis["total_pnl_pct"] = sum(all_pnls)
        analysis["avg_pnl_pct"] = sum(all_pnls) / len(all_pnls) if all_pnls else 0
        analysis["max_winning_trade"] = max(all_pnls) if all_pnls else 0
        analysis["max_losing_trade"] = min(all_pnls) if all_pnls else 0

        # 胜者统计
        if winners:
            winner_pnls = [t.get("pnl_pct", 0) for t in winners]
            analysis["avg_winning_trade"] = sum(winner_pnls) / len(winners)
            analysis["avg_winner_rs_score"] = sum(
                t.get("entry_rs_score", 0) for t in winners
            ) / len(winners)
            analysis["avg_winner_bb_width_pct"] = sum(
                t.get("entry_bb_width_pct", 0) for t in winners
            ) / len(winners)
            analysis["avg_winner_volume_mult"] = sum(
                t.get("entry_volume_mult", 0) for t in winners
            ) / len(winners)

        # 败者统计
        if losers:
            loser_pnls = [t.get("pnl_pct", 0) for t in losers]
            analysis["avg_losing_trade"] = sum(loser_pnls) / len(losers)
            analysis["avg_loser_rs_score"] = sum(
                t.get("entry_rs_score", 0) for t in losers
            ) / len(losers)
            analysis["avg_loser_bb_width_pct"] = sum(
                t.get("entry_bb_width_pct", 0) for t in losers
            ) / len(losers)
            analysis["avg_loser_volume_mult"] = sum(
                t.get("entry_volume_mult", 0) for t in losers
            ) / len(losers)

        # 盈亏比和利润因子
        if winners and losers and analysis.get("avg_losing_trade", 0) != 0:
            analysis["profit_loss_ratio"] = abs(
                analysis["avg_winning_trade"] / analysis["avg_losing_trade"]
            )

            total_wins = sum([t.get("pnl_pct", 0) for t in winners])
            total_losses = abs(sum([t.get("pnl_pct", 0) for t in losers]))
            if total_losses > 0:
                analysis["profit_factor"] = total_wins / total_losses

        # 详细分析（胜者 vs 败者对比）
        detailed_analysis = {}
        if winners and losers:
            detailed_analysis["winners"] = {
                "count": len(winners),
                "avg_pnl_pct": analysis.get("avg_winning_trade", 0),
                "avg_rs_score": analysis.get("avg_winner_rs_score", 0),
                "avg_bb_width_pct": analysis.get("avg_winner_bb_width_pct", 0),
                "avg_volume_mult": analysis.get("avg_winner_volume_mult", 0),
            }
            detailed_analysis["losers"] = {
                "count": len(losers),
                "avg_pnl_pct": analysis.get("avg_losing_trade", 0),
                "avg_rs_score": analysis.get("avg_loser_rs_score", 0),
                "avg_bb_width_pct": analysis.get("avg_loser_bb_width_pct", 0),
                "avg_volume_mult": analysis.get("avg_loser_volume_mult", 0),
            }

        result_dict["trade_metrics"]["analysis"] = analysis
        result_dict["trade_metrics"]["detailed_analysis"] = detailed_analysis

    # ===== 添加性能摘要（整合关键指标，方便快速查看） =====
    # 这个部分从各个详细数据中提取关键指标，便于：
    # 1. AI 快速评估回测结果
    # 2. 人工快速浏览 JSON 时了解整体表现
    # 3. 与 current_backtest_result 对应，用于 LangGraph State
    performance_summary = {
        "total_trades": result.total_positions,
        "total_orders": result.total_orders,
        "elapsed_time_seconds": result.elapsed_time,
    }

    # 从 returns 中提取关键指标
    if result.stats_returns:
        for key, val in result.stats_returns.items():
            if "Sharpe Ratio" in str(key):
                performance_summary["sharpe_ratio"] = val if val == val else None
            elif "Max Drawdown" in str(key):
                performance_summary["max_drawdown"] = val if val == val else None
            elif "Total Return" in str(key):
                performance_summary["total_return"] = val if val == val else None

    # 从交易分析中提取关键指标
    if trade_metrics:
        analysis = result_dict["trade_metrics"]["analysis"]
        performance_summary["win_rate"] = analysis.get("win_rate", 0)
        performance_summary["profit_loss_ratio"] = analysis.get("profit_loss_ratio", 0)
        performance_summary["avg_winning_trade"] = analysis.get("avg_winning_trade", 0)
        performance_summary["avg_losing_trade"] = analysis.get("avg_losing_trade", 0)
        performance_summary["total_pnl_pct"] = analysis.get("total_pnl_pct", 0)

    # 从过滤统计中提取信息
    if filter_stats:
        filter_data = result_dict["filter_stats"]
        performance_summary["total_signals"] = filter_data["total"].get(
            "signal_checks", 0
        )
        performance_summary["signals_passed"] = filter_data["total"].get(
            "all_passed", 0
        )
        if "rates" in filter_data:
            performance_summary["signal_pass_rate"] = filter_data["rates"].get(
                "pass_rate", 0
            )

    result_dict["performance"] = performance_summary

    return result_dict


def _save_results_to_json(
    result_dict: Dict[str, Any],
    strategy_name: str,
    base_dir: Path,
) -> Path:
    """
    将回测结果保存为 JSON 文件。

    文件命名格式: {策略名称}_{YYYY-MM-DD_HH-MM-SS}.json
    存放路径: log/backtest/result/

    Args:
        result_dict: 完整的结果字典
        strategy_name: 策略名称
        base_dir: 项目根目录

    Returns:
        保存的文件路径
    """
    # 创建目录
    result_dir = base_dir / "log" / "backtest" / "result"
    result_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{strategy_name}_{timestamp}.json"
    # filename = f"{strategy_name}"
    filepath = result_dir / filename

    # 保存 JSON
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False, default=str)

    return filepath


def _print_results(
    result: BacktestResult,
    strategy_config: Optional[Dict[str, Any]] = None,
):
    """
    打印回测结果摘要到终端（简化版）

    目标：保持终端输出简洁，只显示核心性能指标
    完整数据（包括策略配置、交易明细等）已保存到 JSON 文件中

    Args:
        result: 回测结果对象
        strategy_config: 策略配置（已移除，设为 None 以简化输出）
    """
    print("\n" + "=" * 65)
    print("🏆 Backtest Report")
    print("=" * 65)
    print(f"Duration:       {result.elapsed_time:.4f}s")
    print(f"Orders:         {result.total_orders}")
    print(f"Positions:      {result.total_positions}")

    if result.stats_pnls:
        for currency, metrics in result.stats_pnls.items():
            print(f"💰 PnL ({currency}):")
            for k, v in metrics.items():
                if v == v:  # Check for NaN
                    print(f"   * {k:<25}: {v:,.4f}")

    if result.stats_returns:
        for currency, val in result.stats_returns.items():
            print(f"- {currency:<25} {val:,.4f}")

    # 注意：策略配置参数已保存到 JSON 文件中，终端不再打印
    # 原因：
    # 1. 保持终端输出简洁，只显示关键性能指标
    # 2. 策略配置可能有几十个参数，会使终端输出过长
    # 3. AI 可以从 JSON 文件中读取完整配置进行分析
    # 4. 人工查看时也更倾向于查看 JSON 文件而非终端滚动输出

    print("=" * 65 + "\n")


def catalog_loader(
    catalog: ParquetDataCatalog,
    csv_path: Path,
    instrument: Instrument,
    bar_type: BarType,
) -> None:
    """
    将 CSV 数据导入 Catalog (Parquet)。

    注意：调用前应先检查数据是否已存在，避免重复解析巨大的 CSV。
    检查逻辑已移至 run_high_level 主循环中，以减少冗余函数调用。
    """
    # 日志输出已移至调用方，此处不再打印

    # 1. 读取前几行检查列名（兼容 "datetime" 和 "timestamp" 两种列名）
    sample_df = pd.read_csv(csv_path, nrows=5)

    # 确定时间列名（优先使用 datetime，兼容 timestamp）
    if "datetime" in sample_df.columns:
        time_col = "datetime"
    elif "timestamp" in sample_df.columns:
        time_col = "timestamp"
    else:
        raise ValueError(
            f"No valid time column found in {csv_path}. "
            f"Expected 'datetime' or 'timestamp', got: {list(sample_df.columns)}"
        )

    # 2. 高效加载 CSV（使用检测到的列名）
    # 注意：必须使用 index_col='<time_col>' 而非 index_col=0
    # 因为 usecols 会改变列的相对位置，index_col=0 会错误地把 'open' 作为索引
    df: DataFrame = CSVBarDataLoader.load(
        file_path=csv_path,
        index_col=time_col,  # 动态使用检测到的列名
        usecols=[time_col, "open", "high", "low", "close", "volume"],
        parse_dates=True,
    )
    df.sort_index(inplace=True)

    # 3. 转换并写入
    # Wrangler 将 DataFrame 转换为 NT 内部的 Bar 序列
    wrangler = BarDataWrangler(bar_type, instrument)

    # 写入标的信息 (NT 的写入是幂等的，多次写入同一个 Instrument 不会报错)
    catalog.write_data([instrument])

    # 写入 Bar 数据
    catalog.write_data(wrangler.process(df))

    # 4. 轻量级校验
    intervals = catalog.get_intervals(data_cls=Bar, identifier=str(bar_type))
    if not intervals:
        raise ValueError(f"❌ Failed to verify data in catalog for {instrument.id}")


# 注意：自定义数据（OI, Funding Rate）现在通过 OIFundingDataLoader 直接加载
# 不再需要序列化到 Parquet Catalog
