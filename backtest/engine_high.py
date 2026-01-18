import gc
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    results = node.run()

    print("✅ Backtest Complete.")

    # 获取策略过滤器统计和交易指标
    filter_stats = None
    trade_metrics = None
    try:
        from strategy.rs_squeeze import RSSqueezeStrategy

        # 获取统计数据（在打印之前）
        filter_stats = RSSqueezeStrategy.get_filter_stats_summary()
        trade_metrics = RSSqueezeStrategy.get_trade_metrics()

        # 输出策略过滤器统计汇总报告
        RSSqueezeStrategy.print_filter_stats_report()
        # 重置类变量，避免多次回测数据累积
        RSSqueezeStrategy.reset_class_stats()
    except ImportError:
        pass  # 非 RS Squeeze 策略时跳过
    except AttributeError:
        pass  # 策略没有该方法时跳过

    # 获取 Universe 文件路径和策略配置参数
    # 注意：cfg.strategy.params 可能是 dict 或 Pydantic 对象
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

    # 构建回测配置信息
    backtest_config = {
        "start_date": str(cfg.start_date),
        "end_date": str(cfg.end_date),
        "initial_balances": cfg.initial_balances,
        "instruments_count": len(loaded_instruments),
        "data_feeds_count": len(cfg.data_feeds),
        "strategies_count": len(strategies),
    }

    # 打印回测结果摘要并保存为 JSON
    if results:
        for result in results:
            # 终端输出
            _print_results(
                result,
                strategy_config=strategy_config,
            )

            # 构建完整结果字典
            result_dict = _build_result_dict(
                result=result,
                strategy_name=cfg.strategy.name,
                strategy_config=strategy_config,
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
            print(f"📁 Results saved to: {json_path}")


def _build_result_dict(
    result: BacktestResult,
    strategy_name: str,
    strategy_config: Optional[Dict[str, Any]] = None,
    filter_stats: Optional[Dict[str, Dict[str, int]]] = None,
    trade_metrics: Optional[List[Dict]] = None,
    backtest_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    构建完整的回测结果字典，用于 JSON 保存和终端输出。

    Args:
        result: BacktestResult 对象
        strategy_name: 策略名称
        strategy_config: 策略配置参数
        filter_stats: 过滤器统计 (来自策略类变量)
        trade_metrics: 交易指标 (来自策略类变量)
        backtest_config: 回测配置信息

    Returns:
        完整的结果字典
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
        },
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

    # 处理过滤器统计
    if filter_stats:
        # 汇总所有实例的统计
        total_stats = {}
        for inst_id, stats in filter_stats.items():
            for key, value in stats.items():
                total_stats[key] = total_stats.get(key, 0) + value
        result_dict["filter_stats"] = {
            "by_instrument": filter_stats,
            "total": total_stats,
        }

    # 处理交易指标分析
    if trade_metrics:
        winners = [t for t in trade_metrics if t.get("result") == "WINNER"]
        losers = [t for t in trade_metrics if t.get("result") == "LOSER"]

        analysis = {
            "total_trades": len(trade_metrics),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate": len(winners) / len(trade_metrics) if trade_metrics else 0,
        }

        if winners:
            analysis["avg_winner_pnl_pct"] = sum(
                t.get("pnl_pct", 0) for t in winners
            ) / len(winners)
            analysis["avg_winner_rs_score"] = sum(
                t.get("entry_rs_score", 0) for t in winners
            ) / len(winners)
            analysis["avg_winner_bb_width_pct"] = sum(
                t.get("entry_bb_width_pct", 0) for t in winners
            ) / len(winners)
            analysis["avg_winner_volume_mult"] = sum(
                t.get("entry_volume_mult", 0) for t in winners
            ) / len(winners)

        if losers:
            analysis["avg_loser_pnl_pct"] = sum(
                t.get("pnl_pct", 0) for t in losers
            ) / len(losers)
            analysis["avg_loser_rs_score"] = sum(
                t.get("entry_rs_score", 0) for t in losers
            ) / len(losers)
            analysis["avg_loser_bb_width_pct"] = sum(
                t.get("entry_bb_width_pct", 0) for t in losers
            ) / len(losers)
            analysis["avg_loser_volume_mult"] = sum(
                t.get("entry_volume_mult", 0) for t in losers
            ) / len(losers)

        if winners and losers and analysis.get("avg_loser_pnl_pct", 0) != 0:
            analysis["rr_ratio"] = abs(
                analysis["avg_winner_pnl_pct"] / analysis["avg_loser_pnl_pct"]
            )

        result_dict["trade_metrics"]["analysis"] = analysis

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
    """打印回测结果摘要，包含 Universe 路径和策略配置"""
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

    # 打印策略配置（供 AI 分析使用）
    if strategy_config:
        print("-" * 65)
        print("📋 Strategy Config (for AI feedback):")
        # 使用 JSON 格式输出，紧凑但可读
        config_json = json.dumps(strategy_config, indent=2, default=str)
        print(config_json)

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

    # 3. 高效加载 CSV
    # 注意：必须使用 index_col='datetime' 而非 index_col=0
    # 因为 usecols 会改变列的相对位置，index_col=0 会错误地把 'open' 作为索引
    df: DataFrame = CSVBarDataLoader.load(
        file_path=csv_path,
        index_col="datetime",
        usecols=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=True,
    )
    df.sort_index(inplace=True)

    # 4. 转换并写入
    # Wrangler 将 DataFrame 转换为 NT 内部的 Bar 序列
    wrangler = BarDataWrangler(bar_type, instrument)

    # 写入标的信息 (NT 的写入是幂等的，多次写入同一个 Instrument 不会报错)
    catalog.write_data([instrument])

    # 写入 Bar 数据
    catalog.write_data(wrangler.process(df))

    # 5. 轻量级校验
    intervals = catalog.get_intervals(data_cls=Bar, identifier=str(bar_type))
    if not intervals:
        raise ValueError(f"❌ Failed to verify data in catalog for {instrument.id}")
