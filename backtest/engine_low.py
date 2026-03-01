import gc
import json
import logging
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
from nautilus_trader.analysis.tearsheet import create_tearsheet
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models.fee import MakerTakerFeeModel
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.config import RiskEngineConfig
from nautilus_trader.core.nautilus_pyo3 import millis_to_nanos
from nautilus_trader.model import BarType, TraderId
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import FundingRateUpdate
from nautilus_trader.model.enums import (
    AccountType,
    BarAggregation,
    BookType,
    OmsType,
)
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.wranglers import BarDataWrangler
import pandas as pd
from pandas import DataFrame

from core.exceptions import (
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
from utils.data_file_checker import check_single_data_file
from utils.data_management.data_loader import load_ohlcv_auto
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

    data_path = data_cfg.full_path
    if not data_path.exists():
        raise DataLoadError(f"Data file not found: {data_path}", str(data_path))

    # 调试日志：输出实际加载的文件路径
    logger.info(f"🔍 Loading {inst_id_str} from: {data_path}")

    try:
        # 使用自动格式检测加载器（支持 CSV 和 Parquet）
        df: DataFrame = load_ohlcv_auto(
            file_path=data_path,
            start_date=cfg.start_date,
            end_date=cfg.end_date,
        )

        if len(df) == 0:
            raise DataLoadError(
                f"No data available in range for {data_cfg.csv_file_name}", str(data_path)
            )

        # 确保 timestamp 列存在（用于验证），同时保持 DatetimeIndex（用于 Wrangler）
        if "timestamp" not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                # 将索引转换为 Unix 时间戳（毫秒）作为 timestamp 列
                df["timestamp"] = (df.index.astype("int64") // 10**6).astype("int64")
            elif hasattr(df.index, "name") and df.index.name == "timestamp":
                # 索引名为 timestamp，转换���数值
                df["timestamp"] = (df.index.astype("int64") // 10**6).astype("int64")

        # 验证数据质量：检查必需列和数据有效性
        required_columns = ["timestamp", "open", "high", "low", "close", "volume"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise DataLoadError(
                f"Missing required columns in {data_cfg.csv_file_name}: {missing_columns}",
                str(data_path),
            )

        # 检查价格列是否包含 NaN 或无效值
        price_columns = ["open", "high", "low", "close"]
        for col in price_columns:
            if df[col].isna().any():
                raise DataLoadError(
                    f"Column '{col}' contains NaN values in {data_cfg.csv_file_name}",
                    str(data_path),
                )
            if (df[col] <= 0).any():
                raise DataLoadError(
                    f"Column '{col}' contains non-positive values in {data_cfg.csv_file_name}",
                    str(data_path),
                )

        # 检查 OHLC 逻辑关系：high >= low, high >= open/close, low <= open/close
        if (df["high"] < df["low"]).any():
            raise DataLoadError(
                f"Invalid OHLC data: high < low in {data_cfg.csv_file_name}",
                str(data_path),
            )
        if (df["high"] < df["open"]).any() or (df["high"] < df["close"]).any():
            raise DataLoadError(
                f"Invalid OHLC data: high < open or close in {data_cfg.csv_file_name}",
                str(data_path),
            )
        if (df["low"] > df["open"]).any() or (df["low"] > df["close"]).any():
            raise DataLoadError(
                f"Invalid OHLC data: low > open or close in {data_cfg.csv_file_name}",
                str(data_path),
            )

        # 使用 Wrangler 转换并注入引擎
        wrangler = BarDataWrangler(feed_bar_type, inst)
        bars = wrangler.process(df)
        engine.add_data(bars)

        file_format = data_path.suffix.upper()[1:]  # .csv -> CSV, .parquet -> PARQUET
        logger.info(f"✅ Loaded {len(bars)} bars for {inst.id} ({data_cfg.label}) [{file_format}]")
        return feed_bar_type

    except Exception as e:
        if isinstance(e, DataLoadError):
            raise
        # 使用 from e 保留原始异常链和堆栈跟踪
        raise DataLoadError(
            f"Error loading {data_cfg.csv_file_name}: {e}", str(data_path), e
        ) from e


def _get_symbol_from_instrument(instrument_id) -> str:
    """从instrument_id提取符号（保留 -PERP 后缀以正确定位数据目录）"""
    if not instrument_id:
        raise ValueError("instrument_id cannot be None or empty")

    if not hasattr(instrument_id, "symbol"):
        raise ValueError(f"Invalid instrument_id type: {type(instrument_id)}")

    # 对于 PERP 标的，保留完整的 symbol（包括 -PERP）
    # 因为资金费率数据存储在 BTCUSDT-PERP 目录下
    symbol_str = str(instrument_id.symbol)
    return symbol_str  # 返回完整的 symbol，例如 "BTCUSDT-PERP" 或 "BTCUSDT"


def _find_custom_data_files(symbol_dir: Path) -> tuple[list, list]:
    """查找OI和Funding数据文件"""
    oi_files = list(symbol_dir.glob("*-oi-1h-*.csv"))
    funding_files = list(symbol_dir.glob("*-funding_rate-*.csv"))
    return oi_files, funding_files


def _load_oi_data_for_symbol(
    loader: OIFundingDataLoader, oi_files: list, symbol: str, instrument_id, cfg: BacktestConfig
) -> list:
    """加载OI数据"""
    oi_data_list = []
    if oi_files:
        for oi_file in oi_files:
            # 确保日期不为 None
            if cfg.start_date and cfg.end_date:
                oi_data_list.extend(
                    loader.load_oi_data(
                        symbol=symbol,
                        instrument_id=instrument_id,
                        start_date=cfg.start_date,
                        end_date=cfg.end_date,
                        exchange=cfg.instrument.venue_name.lower() if cfg.instrument else "binance",
                    )
                )
    return oi_data_list


def _load_funding_data_for_symbol(
    loader: OIFundingDataLoader,
    funding_files: list,
    symbol: str,
    instrument_id,
    cfg: BacktestConfig,
) -> List[FundingRateUpdate]:
    """加载Funding Rate数据"""
    funding_data_list = []
    if funding_files:
        for funding_file in funding_files:
            try:
                df = pd.read_csv(funding_file)

                # 添加大小限制检查
                MAX_ROWS = 100000  # ~11 年的 8 小时资金费率数据
                if len(df) > MAX_ROWS:
                    logger.warning(
                        f"Funding data file too large: {len(df)} rows, truncating to {MAX_ROWS}"
                    )
                    df = df.head(MAX_ROWS)

                # 验证数据格式
                if "timestamp" not in df.columns or "funding_rate" not in df.columns:
                    continue

                # 转换为 FundingRateUpdate 对象
                for _, row in df.iterrows():
                    # 处理 timestamp：可能是字符串或整数
                    ts_value = row["timestamp"]
                    if isinstance(ts_value, str):
                        # 字符串格式，转换为 Unix 毫秒时间��
                        ts_ms = int(pd.to_datetime(ts_value).timestamp() * 1000)
                    else:
                        ts_ms = int(ts_value)

                    ts_event = millis_to_nanos(ts_ms)
                    funding_rate = Decimal(str(row["funding_rate"]))

                    next_funding_time = None
                    if "next_funding_time" in df.columns and pd.notna(row["next_funding_time"]):
                        next_ts_value = row["next_funding_time"]
                        if isinstance(next_ts_value, str):
                            next_ts_ms = int(pd.to_datetime(next_ts_value).timestamp() * 1000)
                        else:
                            next_ts_ms = int(next_ts_value)
                        next_funding_time = millis_to_nanos(next_ts_ms)

                    funding_data = FundingRateUpdate(
                        instrument_id=instrument_id,
                        rate=funding_rate,
                        next_funding_ns=next_funding_time,
                        ts_event=ts_event,
                        ts_init=ts_event,
                    )
                    funding_data_list.append(funding_data)

            except Exception as e:
                logger.warning(f"Error loading {funding_file}: {e}")

    return funding_data_list


def _process_instrument_custom_data(
    inst, data_dir: Path, cfg: BacktestConfig, engine: BacktestEngine
) -> int:
    """处理单个标的的自定义数据"""
    from utils.oi_funding_adapter import merge_custom_data_with_bars

    instrument_id = inst.id
    symbol = _get_symbol_from_instrument(instrument_id)
    symbol_dir = data_dir / symbol

    logger.debug(f"   🔍 Checking custom data for {instrument_id} in {symbol_dir}")

    if not symbol_dir.exists():
        logger.debug(f"   ⚠️ Directory not found: {symbol_dir}")
        return 0

    # 查找数据文件
    oi_files, funding_files = _find_custom_data_files(symbol_dir)
    logger.debug(f"   📁 Found {len(oi_files)} OI files, {len(funding_files)} funding files")

    # 加载数据
    loader = OIFundingDataLoader(data_dir)
    oi_data_list = _load_oi_data_for_symbol(loader, oi_files, symbol, instrument_id, cfg)
    funding_data_list = _load_funding_data_for_symbol(
        loader, funding_files, symbol, instrument_id, cfg
    )

    # 合并并添加到引擎
    if oi_data_list or funding_data_list:
        merged_data = merge_custom_data_with_bars(oi_data_list, funding_data_list)
        from nautilus_trader.model.identifiers import ClientId

        # 重要：使用 add_data() 并确保数据被排序
        # BacktestEngine 会在 run() 时自动回放所有添加的数据
        engine.add_data(merged_data, client_id=ClientId("BINANCE"), sort=True)

        logger.info(f"   ✅ Added {len(merged_data)} custom data points for {symbol}")
        logger.debug(f"   📊 Data types: {set(type(d).__name__ for d in merged_data)}")
        logger.debug(f"   ⏰ Time range: {merged_data[0].ts_event} to {merged_data[-1].ts_event}")
        return len(merged_data)

    return 0


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
        data_dir = base_dir / "data" / "raw"
        total_loaded = 0

        for inst_id_str, inst in loaded_instruments.items():
            total_loaded += _process_instrument_custom_data(inst, data_dir, cfg, engine)

        logger.info(f"✅ Total custom data loaded: {total_loaded} points")
        return total_loaded

    except Exception as e:
        raise CustomDataError(f"Custom data loading failed: {e}", cause=e)


def _extract_strategy_config(cfg: BacktestConfig) -> Dict[str, Any]:
    """提取策略配置"""
    strategy_params = cfg.strategy.params
    if hasattr(strategy_params, "model_dump"):
        return strategy_params.model_dump()  # type: ignore[no-any-return]
    elif hasattr(strategy_params, "dict"):
        return strategy_params.dict()  # type: ignore[no-any-return]
    elif isinstance(strategy_params, dict):
        return strategy_params
    return {}


def _get_order_position_stats(engine: BacktestEngine) -> tuple[int, int]:
    """获取订单和持仓统计"""
    orders_report = engine.trader.generate_order_fills_report()
    positions_report = engine.trader.generate_positions_report()

    total_orders = (
        len(orders_report) if orders_report is not None and hasattr(orders_report, "__len__") else 0
    )
    total_positions = (
        len(positions_report)
        if positions_report is not None and hasattr(positions_report, "__len__")
        else 0
    )

    return total_orders, total_positions


def _find_pnl_column(positions_report):
    """查找PnL列名"""
    for col in ["realized_pnl", "pnl", "realized_return", "return"]:
        if col in positions_report.columns:
            return col
    return None


def _calculate_pnl_stats(realized_pnls) -> dict:
    """计算PnL统计指标"""
    winners = realized_pnls[realized_pnls > 0]
    losers = realized_pnls[realized_pnls < 0]
    total_pnl = float(realized_pnls.sum())

    return {
        "PnL (total)": total_pnl,
        "PnL% (total)": total_pnl,
        "Max Winner": float(winners.max()) if len(winners) > 0 else None,
        "Avg Winner": float(winners.mean()) if len(winners) > 0 else None,
        "Min Winner": float(winners.min()) if len(winners) > 0 else None,
        "Min Loser": float(losers.min()) if len(losers) > 0 else None,
        "Avg Loser": float(losers.mean()) if len(losers) > 0 else None,
        "Max Loser": float(losers.max()) if len(losers) > 0 else None,
        "Expectancy": float(realized_pnls.mean()) if len(realized_pnls) > 0 else None,
        "Win Rate": float(len(winners) / len(realized_pnls)) if len(realized_pnls) > 0 else None,
    }


def _calculate_basic_stats(returns):
    """计算基础统计指标"""
    import numpy as np

    avg_return = float(np.mean(returns))
    std_return = float(np.std(returns))
    return avg_return, std_return


def _calculate_sharpe_ratio(avg_return: float, std_return: float) -> float:
    """计算夏普比率"""
    import numpy as np

    return float(avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0


def _calculate_sortino_ratio(returns, avg_return: float) -> float:
    """计算索提诺比率"""
    import numpy as np

    downside_returns = returns[returns < 0]
    downside_std = float(np.std(downside_returns)) if len(downside_returns) > 0 else 0
    return float(avg_return / downside_std * np.sqrt(252)) if downside_std > 0 else 0


def _calculate_profit_factor(winners, losers) -> float:
    """计算盈利因子"""
    avg_win = float(winners.mean()) if len(winners) > 0 else 0
    avg_loss = abs(float(losers.mean())) if len(losers) > 0 else 0
    return float(avg_win / avg_loss) if avg_loss > 0 else 0


def _calculate_returns_stats(realized_pnls) -> dict:
    """计算收益率统计指标"""
    if len(realized_pnls) <= 1:
        return {}

    import numpy as np

    returns = realized_pnls.values
    winners = realized_pnls[realized_pnls > 0]
    losers = realized_pnls[realized_pnls < 0]

    avg_return, std_return = _calculate_basic_stats(returns)
    sharpe = _calculate_sharpe_ratio(avg_return, std_return)
    sortino = _calculate_sortino_ratio(returns, avg_return)
    profit_factor = _calculate_profit_factor(winners, losers)

    avg_win = float(winners.mean()) if len(winners) > 0 else 0
    avg_loss = float(losers.mean()) if len(losers) > 0 else None
    risk_return = float(std_return / abs(avg_return)) if avg_return != 0 else None

    return {
        "Returns Volatility (252 days)": std_return * np.sqrt(252),
        "Average (Return)": avg_return,
        "Average Loss (Return)": avg_loss,
        "Average Win (Return)": avg_win,
        "Sharpe Ratio (252 days)": sharpe,
        "Sortino Ratio (252 days)": sortino,
        "Profit Factor": profit_factor,
        "Risk Return Ratio": risk_return,
    }


def _extract_pnl_from_positions(positions_report) -> dict:
    """从持仓报告中提取PnL统计"""
    stats_pnls: Dict[str, Any] = {}

    try:
        if (
            positions_report is None
            or not hasattr(positions_report, "empty")
            or positions_report.empty
        ):
            return stats_pnls

        logger.debug(f"持仓报告列: {positions_report.columns.tolist()}")

        pnl_column = _find_pnl_column(positions_report)
        if not pnl_column:
            logger.warning(f"持仓报告中未找到 PnL 列，可用列: {positions_report.columns.tolist()}")
            return stats_pnls

        realized_pnls = positions_report[pnl_column].dropna()
        if len(realized_pnls) == 0:
            return stats_pnls

        stats_pnls["USDT"] = _calculate_pnl_stats(realized_pnls)

    except Exception as e:
        logger.warning(f"计算统计指标时出错: {e}")

    return stats_pnls


def _build_result_dict(
    cfg: BacktestConfig,
    strategy_config: dict,
    total_orders: int,
    total_positions: int,
    stats_pnls: dict,
    engine_pnl: float,
    funding_collected: Decimal,
    initial_capital: float,
) -> dict:
    """构建结果字典"""
    # 计算真实 PnL
    funding_float = float(funding_collected)
    real_pnl = engine_pnl + funding_float
    real_return_pct = (real_pnl / initial_capital * 100) if initial_capital > 0 else 0

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
            "engine_pnl": engine_pnl,
            "funding_collected": funding_float,
            "real_pnl": real_pnl,
            "real_return_pct": real_return_pct,
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
            "engine_pnl": engine_pnl,
            "funding_collected": funding_float,
            "real_pnl": real_pnl,
            "real_return_pct": real_return_pct,
        },
    }

    if stats_pnls:
        pnl_dict: Dict[str, Any] = result_dict["pnl"]  # type: ignore[assignment]
        for currency, metrics in stats_pnls.items():
            pnl_dict[str(currency)] = {str(k): v if v == v else None for k, v in metrics.items()}

    return result_dict


def _add_returns_to_result(engine: BacktestEngine, result_dict: dict) -> None:
    """添加收益率指标到结果字典"""
    try:
        returns_stats = engine.trader.generate_returns_report()
        if returns_stats:
            for key, val in returns_stats.items():
                result_dict["returns"][str(key)] = val if val == val else None
    except (AttributeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to generate returns report: {e}")


def _save_result_json(cfg: BacktestConfig, base_dir: Path, result_dict: dict) -> None:
    """保存结果到JSON文件"""
    result_dir = base_dir / "output" / "backtest" / "result"
    result_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{cfg.strategy.name}_{timestamp}.json"
    filepath = result_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"📁 Results saved to: {filepath}")


def _extract_funding_collected(engine: BacktestEngine) -> Decimal:
    """从策略实例中提取资金费率收益"""
    total_funding = Decimal("0")

    try:
        # 遍历所有策略实例
        for strategy in engine.trader.strategies():
            # 检查策略是否有 _total_funding_collected 属性
            if hasattr(strategy, "_total_funding_collected"):
                funding = strategy._total_funding_collected
                if funding:
                    total_funding += funding
                    logger.info(
                        f"💰 Extracted funding from {strategy.__class__.__name__}: {float(funding):.2f} USDT"
                    )
    except Exception as e:
        logger.warning(f"⚠️ Failed to extract funding collected: {e}")

    return total_funding


def _calculate_engine_pnl(cfg: BacktestConfig, engine: BacktestEngine) -> tuple[float, float]:
    """计算引擎层面的 PnL 和初始资金"""
    initial_capital = sum(float(b.as_decimal()) for b in cfg.initial_balances)

    # 获取最终账户余额
    venue_name = cfg.instrument.venue_name if cfg.instrument else "BINANCE"
    venue = Venue(venue_name)
    account = engine.trader.generate_account_report(venue)

    if account is not None and not account.empty:
        # 从账户报告中提取最终余额
        final_balance = (
            float(account.iloc[-1]["total"]) if "total" in account.columns else initial_capital
        )
    else:
        final_balance = initial_capital

    engine_pnl = final_balance - initial_capital
    return engine_pnl, initial_capital


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
        strategy_config = _extract_strategy_config(cfg)
        total_orders, total_positions = _get_order_position_stats(engine)

        positions_report = engine.trader.generate_positions_report()
        stats_pnls = _extract_pnl_from_positions(positions_report)

        # 提取资金费率收益
        funding_collected = _extract_funding_collected(engine)

        # 计算引擎 PnL
        engine_pnl, initial_capital = _calculate_engine_pnl(cfg, engine)

        result_dict = _build_result_dict(
            cfg,
            strategy_config,
            total_orders,
            total_positions,
            stats_pnls,
            engine_pnl,
            funding_collected,
            initial_capital,
        )
        _add_returns_to_result(engine, result_dict)
        _save_result_json(cfg, base_dir, result_dict)

        # 输出真实 PnL 摘要
        real_pnl = engine_pnl + float(funding_collected)
        real_return_pct = (real_pnl / initial_capital * 100) if initial_capital > 0 else 0

        logger.info(
            f"\n{'=' * 60}\n"
            f"📊 Backtest Results Summary\n"
            f"{'=' * 60}\n"
            f"Initial Capital: {initial_capital:.2f} USDT\n"
            f"Engine PnL: {engine_pnl:.2f} USDT\n"
            f"Funding Collected: {float(funding_collected):.2f} USDT\n"
            f"Real PnL: {real_pnl:.2f} USDT ({real_return_pct:+.2f}%)\n"
            f"{'=' * 60}"
        )

    except Exception as e:
        logger.warning(f"⚠️ Error saving results: {e}")


def _setup_engine(cfg: BacktestConfig, base_dir: Path) -> BacktestEngine:
    """初始化回测引擎"""
    logging_config = None
    if cfg.logging:
        logging_config = LoggingConfig(
            log_level=cfg.logging.log_level,
            log_level_file=cfg.logging.log_level_file,
            log_directory=str(base_dir / "log" / "backtest" / "low_level"),
        )

    engine = BacktestEngine(
        BacktestEngineConfig(
            trader_id=TraderId("BACKTESTER-001"),
            logging=logging_config,
            risk_engine=RiskEngineConfig(bypass=False),
        )
    )

    venue_name = cfg.instrument.venue_name if cfg.instrument else "BINANCE"
    oms_type_str = getattr(
        cfg.strategy.params if hasattr(cfg.strategy, "params") else {}, "oms_type", "HEDGING"
    )
    oms_type = OmsType.HEDGING if oms_type_str == "HEDGING" else OmsType.NETTING

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

    return engine


def _filter_instruments_with_data(cfg: BacktestConfig, base_dir: Path) -> List:
    """过滤有数据的标的"""
    from core.schemas import InstrumentConfig, InstrumentType

    instruments_with_data = []

    if not cfg.start_date or not cfg.end_date:
        logger.warning("⚠️ start_date 或 end_date 未配置，跳过数据可用性检查")
        return list(cfg.instruments)

    for inst_cfg in cfg.instruments:
        symbol = (
            inst_cfg.instrument_id.split("-")[0]
            if "-" in inst_cfg.instrument_id
            else inst_cfg.instrument_id.split(".")[0]
        )

        if cfg.data_feeds:
            first_feed = cfg.data_feeds[0]
            unit_map = {
                BarAggregation.MINUTE: "m",
                BarAggregation.HOUR: "h",
                BarAggregation.DAY: "d",
            }
            timeframe = f"{first_feed.bar_period}{unit_map.get(first_feed.bar_aggregation, 'h')}"
        else:
            timeframe = "1h"

        has_data, _ = check_single_data_file(
            symbol=symbol,
            start_date=cfg.start_date,
            end_date=cfg.end_date,
            timeframe=timeframe,
            exchange=inst_cfg.venue_name.lower(),
            base_dir=base_dir,
        )

        if has_data:
            instruments_with_data.append(inst_cfg)
        else:
            logger.debug(f"⏭️ Skipping {inst_cfg.instrument_id}: no data file")

    # 自动添加 SPOT 标的（用于资金费率套利策略）
    perp_instruments = [cfg for cfg in instruments_with_data if "-PERP" in cfg.instrument_id]

    for perp_cfg in perp_instruments:
        # 推导 SPOT symbol: BTCUSDT-PERP -> BTCUSDT
        spot_symbol = perp_cfg.instrument_id.split("-")[0]
        spot_id = spot_symbol + "." + perp_cfg.venue_name

        # 检查是否已存在
        if not any(cfg.instrument_id == spot_id for cfg in instruments_with_data):
            # 检查 SPOT 数据是否存在
            has_spot_data, _ = check_single_data_file(
                symbol=spot_symbol,
                start_date=cfg.start_date,
                end_date=cfg.end_date,
                timeframe=timeframe,
                exchange=perp_cfg.venue_name.lower(),
                base_dir=base_dir,
            )

            if has_spot_data:
                # 创建 SPOT 标的配置
                spot_cfg = InstrumentConfig(
                    type=InstrumentType.SPOT,
                    venue_name=perp_cfg.venue_name,
                    base_currency=perp_cfg.base_currency,
                    quote_currency=perp_cfg.quote_currency,
                    leverage=1,
                )
                instruments_with_data.append(spot_cfg)
                logger.info(f"🔄 Auto-added SPOT instrument for funding arbitrage: {spot_id}")
            else:
                logger.warning(
                    f"⚠️ SPOT data not found for {spot_id}, funding arbitrage may not work"
                )

    if not instruments_with_data:
        raise BacktestEngineError("No instruments with available data found")

    logger.info(
        f"📊 Found {len(instruments_with_data)}/{len(cfg.instruments)} instruments with data"
    )
    return instruments_with_data


def _load_instruments(engine: BacktestEngine, instruments_with_data: List) -> Dict:
    """加载标的定义（自动添加 SPOT 标的用于资金费率套利）"""
    from core.schemas import InstrumentConfig, InstrumentType

    # 自动添加 SPOT 标的（用于资金费率套利策略）
    # 如果发现 PERP 标的，自动添加对应的 SPOT 标的
    inst_cfg_list = list(instruments_with_data)  # 转换为列表以便修改
    perp_instruments = [cfg for cfg in inst_cfg_list if "-PERP" in cfg.instrument_id]

    for perp_cfg in perp_instruments:
        # 推导 SPOT ID: BTCUSDT-PERP.BINANCE -> BTCUSDT.BINANCE
        spot_id = perp_cfg.instrument_id.replace("-PERP", "")

        # 检查是否已存在
        if not any(cfg.instrument_id == spot_id for cfg in inst_cfg_list):
            # 创建 SPOT 标的配置
            spot_cfg = InstrumentConfig(
                type=InstrumentType.SPOT,
                venue_name=perp_cfg.venue_name,
                base_currency=perp_cfg.base_currency,
                quote_currency=perp_cfg.quote_currency,
                leverage=1,  # SPOT 不使用杠杆
            )
            inst_cfg_list.append(spot_cfg)
            logger.info(f"🔄 Auto-added SPOT instrument for funding arbitrage: {spot_id}")

    loaded_instruments = {}

    for inst_cfg in inst_cfg_list:
        inst_path = inst_cfg.get_json_path()
        if not inst_path.exists():
            raise InstrumentLoadError(
                f"Instrument path not found: {inst_path}", inst_cfg.instrument_id
            )

        try:
            inst = load_instrument(inst_path)
            engine.add_instrument(inst)
            loaded_instruments[str(inst.id)] = inst
            logger.info(f"✅ Loaded instrument: {inst.id}")
        except Exception as e:
            raise InstrumentLoadError(
                f"Failed to load instrument {inst_cfg.instrument_id}: {e}",
                inst_cfg.instrument_id,
                e,
            )

    return loaded_instruments


def _load_data_feeds(
    engine: BacktestEngine, cfg: BacktestConfig, base_dir: Path, loaded_instruments: Dict
) -> Dict:
    """加载回测数据"""
    from core.schemas import DataConfig

    all_feeds = {}

    # 为自动添加的 SPOT 标的创建数据源配置
    data_feeds_to_load = list(cfg.data_feeds)

    logger.info(f"🔍 Initial data_feeds_to_load: {[f.instrument_id for f in data_feeds_to_load]}")

    # 检查是否有 SPOT 标的需要加载数据
    for inst_id_str in loaded_instruments.keys():
        # 如果是 SPOT 标的且不在现有 data_feeds 中
        is_spot = "-PERP" not in inst_id_str
        has_feed = any(df.instrument_id == inst_id_str for df in data_feeds_to_load)
        logger.info(f"🔍 Checking {inst_id_str}: is_spot={is_spot}, has_feed={has_feed}")

        if is_spot and not has_feed:
            # 查找对应的 PERP 配置作为模板
            perp_id = inst_id_str.replace(".BINANCE", "-PERP.BINANCE")
            perp_feed = next((df for df in cfg.data_feeds if perp_id in df.instrument_id), None)

            if perp_feed:
                # 创建 SPOT 数据源配置（复制 PERP 的配置）
                spot_symbol = inst_id_str.split(".")[0]
                spot_feed = DataConfig(
                    instrument_id=inst_id_str,
                    bar_aggregation=perp_feed.bar_aggregation,
                    bar_period=perp_feed.bar_period,
                    price_type=perp_feed.price_type,
                    origination=perp_feed.origination,
                    csv_file_name=f"{spot_symbol}/binance-{spot_symbol}-1h-{cfg.start_date}_{cfg.end_date}.csv",
                    label="main",
                )
                data_feeds_to_load.append(spot_feed)
                logger.info(f"🔄 Auto-created data feed for SPOT: {inst_id_str}")

    total_feeds = len(data_feeds_to_load)

    for feed_idx, data_cfg in enumerate(data_feeds_to_load, 1):
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
    return all_feeds


def _add_strategies(
    engine: BacktestEngine, cfg: BacktestConfig, all_feeds: Dict, loaded_instruments: Dict
) -> int:
    """配置与添加策略"""
    StrategyClass = load_strategy_class(cfg.strategy.module_path, cfg.strategy.name)
    ConfigClass = load_strategy_config_class(
        cfg.strategy.module_path, cfg.strategy.resolve_config_class()
    )

    global_feeds = {label: bt for (iid, label), bt in all_feeds.items() if label == "benchmark"}
    strategies_count = 0

    # 特殊处理：资金费率套利策略只需要一个实例（基于 PERP 标的）
    is_funding_arbitrage = cfg.strategy.name == "FundingArbitrageStrategy"

    for inst_id, inst in loaded_instruments.items():
        # 如果是资金费率套利策略，跳过 SPOT 标的
        if is_funding_arbitrage and "-PERP" not in inst_id:
            continue

        local_feeds = {
            label: bt
            for (iid, label), bt in all_feeds.items()
            if iid == inst_id and label != "benchmark"
        }

        if "main" not in local_feeds:
            continue

        strat_params = cfg.strategy.resolve_params(
            instrument_id=inst.id,
            leverage=cfg.instrument.leverage if cfg.instrument else 1,
            feed_bar_types={**local_feeds, **global_feeds},
        )

        final_params = filter_strategy_params(strat_params, ConfigClass)
        strat_config = ConfigClass(**final_params)
        engine.add_strategy(StrategyClass(config=strat_config))
        strategies_count += 1

    return strategies_count


def _generate_report(cfg: BacktestConfig, base_dir: Path, engine: BacktestEngine) -> None:
    """生成HTML报告"""
    if cfg.output_html_report:
        output_dir = base_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = (
            output_dir / f"low_{cfg.strategy.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        create_tearsheet(engine=engine, output_path=str(report_path))
        logger.info(f"📊 HTML Report generated: {report_path}")


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
        engine = _setup_engine(cfg, base_dir)
        instruments_with_data = _filter_instruments_with_data(cfg, base_dir)
        loaded_instruments = _load_instruments(engine, instruments_with_data)
        all_feeds = _load_data_feeds(engine, cfg, base_dir, loaded_instruments)

        # 在 bar 数据加载之后、策略添加之前加载自定义数据
        try:
            _load_custom_data_to_engine(cfg, base_dir, engine, loaded_instruments)
        except CustomDataError as e:
            logger.warning(f"⚠️ Custom data loading failed: {e}")

        strategies_count = _add_strategies(engine, cfg, all_feeds, loaded_instruments)

        if strategies_count == 0:
            raise BacktestEngineError(
                "No strategy instances were created. Check config and data paths."
            )

        # 调试：检查引擎中的数据

        logger.info(f"⏳ Running engine with {strategies_count} strategy instances...")
        engine.run()
        logger.info("✅ Backtest Complete.")

        _process_backtest_results(cfg, base_dir, engine)
        _generate_report(cfg, base_dir, engine)

        gc.collect()
        engine.reset()
        engine.dispose()
        logger.info("🧹 Engine resources cleaned up")

    except (InstrumentLoadError, DataLoadError, CustomDataError) as e:
        logger.error(f"❌ Backtest failed: {e}")
        raise
    except Exception as e:
        raise BacktestEngineError(f"Unexpected error during backtest: {e}", e)
