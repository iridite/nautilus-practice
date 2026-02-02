import gc
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)
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
)
from core.schemas import BacktestConfig, DataConfig
from strategy.core.loader import (
    filter_strategy_params,
    load_strategy_class,
    load_strategy_config_class,
)
from utils.data_management.data_loader import load_ohlcv_csv
from utils.instrument_loader import load_instrument
from utils.oi_funding_adapter import OIFundingDataLoader


def _load_data_for_feed(
    engine: BacktestEngine,
    base_dir: Path,
    cfg: BacktestConfig,
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
            csv_path=csv_path,
            start_date=cfg.start_date,
            end_date=cfg.end_date,
        )

        if len(df) == 0:
            raise DataLoadError(f"No data available in range for {data_cfg.csv_file_name}", str(csv_path))

        # 使用 Wrangler 转换并注入引擎
        wrangler = BarDataWrangler(feed_bar_type, inst)
        bars = wrangler.process(df)
        engine.add_data(bars)

        logger.info(f"✅ Loaded {len(bars)} bars for {inst.id} ({data_cfg.label})")
        return feed_bar_type

    except Exception as e:
        if isinstance(e, DataLoadError):
            raise
        raise DataLoadError(f"Error loading {data_cfg.csv_file_name}: {e}", str(csv_path), e)


def _load_custom_data_to_engine(
    cfg: BacktestConfig,
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
        logger.warning("⚠️ No date range specified, skipping custom data loading")
        return 0

    logger.info("📊 Loading custom data (OI, Funding Rate)...")

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
                loader = OIFundingDataLoader(base_dir)
                for oi_file in oi_files:
                    oi_data_list.extend(loader.load_oi_data(
                        symbol=symbol,
                        instrument_id=instrument_id,
                        start_date=cfg.start_date,
                        end_date=cfg.end_date,
                        exchange=cfg.instrument.venue_name.lower() if cfg.instrument else "binance"
                    ))

            # 加载Funding Rate数据
            if funding_files:
                loader = OIFundingDataLoader(base_dir)
                for funding_file in funding_files:
                    funding_data_list.extend(loader.load_funding_data(
                        symbol=symbol,
                        instrument_id=instrument_id,
                        start_date=cfg.start_date,
                        end_date=cfg.end_date,
                        exchange=cfg.instrument.venue_name.lower() if cfg.instrument else "binance"
                    ))

            # 合并并添加到引擎
            if oi_data_list or funding_data_list:
                merged_data = merge_custom_data_with_bars(oi_data_list, funding_data_list)
                engine.add_data(merged_data)
                total_loaded += len(merged_data)
                logger.info(f"   ✅ Added {len(merged_data)} custom data points for {symbol}")

        logger.info(f"✅ Total custom data loaded: {total_loaded} points")
        return total_loaded

    except Exception as e:
        raise CustomDataError(f"Custom data loading failed: {e}", cause=e)




def _process_backtest_results(
    cfg: BacktestConfig,
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
        # 提取策略配置
        strategy_params = cfg.strategy.params
        if hasattr(strategy_params, "model_dump"):
            strategy_config = strategy_params.model_dump()
        elif hasattr(strategy_params, "dict"):
            strategy_config = strategy_params.dict()
        elif isinstance(strategy_params, dict):
            strategy_config = strategy_params
        else:
            strategy_config = {}

        # 获取回测统计数据 - 从 trader 报告中计算
        venue = Venue(cfg.instrument.venue_name) if cfg.instrument else Venue("BINANCE")

        # 获取订单和持仓统计
        orders_report = engine.trader.generate_order_fills_report()
        positions_report = engine.trader.generate_positions_report()
        total_orders = len(orders_report) if orders_report is not None and hasattr(orders_report, '__len__') else 0
        total_positions = len(positions_report) if positions_report is not None and hasattr(positions_report, '__len__') else 0

        # 初始化统计字典
        stats_pnls = {}
        stats_returns = {}

        # 从持仓报告中计算 PnL 统计
        try:
            if positions_report is not None and hasattr(positions_report, 'empty') and not positions_report.empty:
                # 检查可用的列
                logger.debug(f"持仓报告列: {positions_report.columns.tolist()}")

                # 尝试多个可能的 PnL 列名
                pnl_column = None
                for col in ['realized_pnl', 'pnl', 'realized_return', 'return']:
                    if col in positions_report.columns:
                        pnl_column = col
                        break

                if pnl_column:
                    realized_pnls = positions_report[pnl_column].dropna()

                    if len(realized_pnls) > 0:
                        winners = realized_pnls[realized_pnls > 0]
                        losers = realized_pnls[realized_pnls < 0]

                        total_pnl = float(realized_pnls.sum())

                        stats_pnls['USDT'] = {
                            'PnL (total)': total_pnl,
                            'PnL% (total)': total_pnl,
                            'Max Winner': float(winners.max()) if len(winners) > 0 else None,
                            'Avg Winner': float(winners.mean()) if len(winners) > 0 else None,
                            'Min Winner': float(winners.min()) if len(winners) > 0 else None,
                            'Min Loser': float(losers.min()) if len(losers) > 0 else None,
                            'Avg Loser': float(losers.mean()) if len(losers) > 0 else None,
                            'Max Loser': float(losers.max()) if len(losers) > 0 else None,
                            'Expectancy': float(realized_pnls.mean()) if len(realized_pnls) > 0 else None,
                            'Win Rate': float(len(winners) / len(realized_pnls)) if len(realized_pnls) > 0 else None,
                        }

                        # 计算收益率统计
                        if len(realized_pnls) > 1:
                            import numpy as np
                            returns = realized_pnls.values

                            # 计算基本统计
                            avg_return = float(np.mean(returns))
                            std_return = float(np.std(returns))

                            # 计算夏普比率
                            sharpe = float(avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0

                            # 计算索提诺比率
                            downside_returns = returns[returns < 0]
                            downside_std = float(np.std(downside_returns)) if len(downside_returns) > 0 else 0
                            sortino = float(avg_return / downside_std * np.sqrt(252)) if downside_std > 0 else 0

                            # 计算盈亏比
                            avg_win = float(winners.mean()) if len(winners) > 0 else 0
                            avg_loss = abs(float(losers.mean())) if len(losers) > 0 else 0
                            profit_factor = float(avg_win / avg_loss) if avg_loss > 0 else 0

                            stats_returns = {
                                'Returns Volatility (252 days)': std_return * np.sqrt(252),
                                'Average (Return)': avg_return,
                                'Average Loss (Return)': float(losers.mean()) if len(losers) > 0 else None,
                                'Average Win (Return)': avg_win,
                                'Sharpe Ratio (252 days)': sharpe,
                                'Sortino Ratio (252 days)': sortino,
                                'Profit Factor': profit_factor,
                                'Risk Return Ratio': float(std_return / abs(avg_return)) if avg_return != 0 else None,
                            }
                else:
                    logger.warning(f"持仓报告中未找到 PnL 列，可用列: {positions_report.columns.tolist()}")
        except Exception as e:
            logger.warning(f"计算统计指标时出错: {e}")

        # 构建完整结果字典
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
                "total_orders": total_orders,
                "total_positions": total_positions,
            },
            "pnl": {},
            "returns": {},
            "strategy_config": strategy_config,
            "backtest_config": {
                "start_date": str(cfg.start_date),
                "end_date": str(cfg.end_date),
                "initial_balances": [str(b) for b in cfg.initial_balances],
            },
            "performance": {
                "total_orders": total_orders,
                "total_positions": total_positions,
            }
        }

        # 处理 PnL 指标
        if stats_pnls is not None:
            for currency, metrics in stats_pnls.items():
                result_dict["pnl"][str(currency)] = {
                    str(k): v if v == v else None
                    for k, v in metrics.items()
                }

        # 处理收益率指标 - 使用 generate_returns_report 获取统计数据
        try:
            returns_stats = engine.trader.generate_returns_report()
            if returns_stats:
                for key, val in returns_stats.items():
                    result_dict["returns"][str(key)] = val if val == val else None
        except Exception:
            pass

        # 保存 JSON 结果
        result_dir = base_dir / "output" / "backtest" / "result"
        result_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{cfg.strategy.name}_{timestamp}.json"
        filepath = result_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"📁 Results saved to: {filepath}")

    except Exception as e:
        logger.warning(f"⚠️ Error saving results: {e}")


def run_low_level(cfg: BacktestConfig, base_dir: Path):
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
    logger.info(f"🚀 Starting Low-Level Backtest: {cfg.strategy.name}")

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

        # 从策略配置中读取 oms_type
        oms_type_str = getattr(cfg.strategy_config, 'oms_type', 'HEDGING')
        oms_type = OmsType.HEDGING if oms_type_str == 'HEDGING' else OmsType.NETTING

        engine.add_venue(
            venue=Venue(venue_name),
            oms_type=oms_type,
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
                logger.info(f"✅ Loaded instrument: {inst.id}")
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
                logger.error(f"\n❌ Failed to load {data_cfg.csv_file_name}: {e}")
                continue

        logger.info(f"\n✅ Loaded {len(all_feeds)} data feeds")

        # 6. 加载自定义数据 (OI, Funding Rate)
        try:
            _load_custom_data_to_engine(cfg, base_dir, engine, loaded_instruments)
        except CustomDataError as e:
            logger.warning(f"⚠️ Custom data loading failed: {e}")

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

        logger.info(f"⏳ Running engine with {strategies_count} strategy instances...")
        engine.run()
        logger.info("✅ Backtest Complete.")

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
            logger.info(f"📊 HTML Report generated: {report_path}")

        # 10. 清理资源
        gc.collect()
        engine.reset()
        engine.dispose()
        logger.info("🧹 Engine resources cleaned up")

    except (InstrumentLoadError, DataLoadError, CustomDataError) as e:
        logger.error(f"❌ Backtest failed: {e}")
        raise
    except Exception as e:
        raise BacktestEngineError(f"Unexpected error during backtest: {e}", e)
