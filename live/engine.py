"""
统一的 Live Trading 运行框架

基于 YAML 配置文件快速启动实盘交易环境，与 backtest/sandbox 共享配置
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from nautilus_trader.adapters.binance import BINANCE
from nautilus_trader.adapters.binance.config import (
    BinanceDataClientConfig,
    BinanceExecClientConfig,
)
from nautilus_trader.adapters.binance.factories import (
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.adapters.okx import OKX, OKXDataClientConfig, OKXExecClientConfig
from nautilus_trader.adapters.okx.factories import (
    OKXLiveDataClientFactory,
    OKXLiveExecClientFactory,
)
from nautilus_trader.common import Environment
from nautilus_trader.config import (
    CacheConfig,
    InstrumentProviderConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.core.nautilus_pyo3 import OKXContractType, OKXInstrumentType
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import TraderId

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from core.loader import load_config
from utils.instrument_helpers import convert_to_exchange_format, format_aux_instrument_id
from utils.instrument_loader import load_instrument


def load_strategy_instance(strategy_config, instrument_ids):
    """
    动态加载策略实例

    Args:
        strategy_config: 策略配置对象
        instrument_ids: 交易标的列表

    Returns:
        Strategy: 策略实例

    Raises:
        ValueError: 当模块路径不安全、类不存在或参数无效时
        ImportError: 当模块导入失败时
    """
    import importlib

    module_path = strategy_config.module_path
    strategy_name = strategy_config.name
    config_class_name = strategy_config.config_class or f"{strategy_name}Config"

    # 安全验证：只允许从 strategy 模块加载
    if not module_path.startswith("strategy."):
        raise ValueError(
            f"Invalid module path: {module_path}. "
            "Only modules under 'strategy.*' are allowed for security reasons."
        )

    # 验证策略名称格式（防止注入）
    if not strategy_name.replace("_", "").isalnum():
        raise ValueError(
            f"Invalid strategy name: {strategy_name}. "
            "Strategy name must contain only alphanumeric characters and underscores."
        )

    try:
        # 使用 importlib 替代 __import__（更安全）
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(f"Failed to import module '{module_path}': {e}")

    # 验证类是否存在
    if not hasattr(module, strategy_name):
        raise ValueError(f"Strategy class '{strategy_name}' not found in module '{module_path}'")
    if not hasattr(module, config_class_name):
        raise ValueError(f"Config class '{config_class_name}' not found in module '{module_path}'")

    StrategyClass = getattr(module, strategy_name)
    ConfigClass = getattr(module, config_class_name)

    params = strategy_config.parameters.copy()

    if len(instrument_ids) == 1:
        params["instrument_id"] = instrument_ids[0]
    else:
        raise ValueError(
            f"Live trading currently only supports single instrument, got {len(instrument_ids)}"
        )

    # Convert btc_instrument_id to exchange format if it exists
    # ConfigAdapter may have already set btc_instrument_id in NautilusTrader format (BTCUSDT-SWAP.OKX)
    # We need to convert it to exchange format (BTC-USDT-SWAP.OKX for OKX)
    if "btc_instrument_id" in params and params["btc_instrument_id"]:
        inst_id = params["instrument_id"]
        venue = inst_id.split(".")[-1] if "." in inst_id else "BINANCE"
        btc_inst_id = params["btc_instrument_id"]
        params["btc_instrument_id"] = convert_to_exchange_format(btc_inst_id, venue)
    elif "btc_symbol" in params:
        # Fallback: derive btc_instrument_id from btc_symbol if not already set
        inst_id = params["instrument_id"]
        try:
            btc_inst_id = format_aux_instrument_id(
                params["btc_symbol"], template_inst_id=inst_id
            )
            venue = inst_id.split(".")[-1] if "." in inst_id else "BINANCE"
            params["btc_instrument_id"] = convert_to_exchange_format(btc_inst_id, venue)
        except Exception as e:
            raise ValueError(
                f"Failed to format btc_instrument_id for template {inst_id}, btc_symbol={params.get('btc_symbol')}: {e}"
            )

    config = ConfigClass(**params)
    return StrategyClass(config=config)


def build_binance_config(live_cfg, instrument_ids):
    """构建 Binance 配置"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    load_dotenv(env_file)

    api_key = os.getenv(live_cfg.api_key_env)
    api_secret = os.getenv(live_cfg.api_secret_env)

    if not all([api_key, api_secret]):
        raise ValueError("Missing Binance API credentials in environment")

    load_ids = frozenset(instrument_ids)

    data_config = BinanceDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        testnet=False,
    )

    exec_config = BinanceExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        testnet=False,
    )

    return data_config, exec_config


def build_okx_config(live_cfg, instrument_ids):
    """构建 OKX 配置"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        raise FileNotFoundError(f"Environment file not found: {env_file}")

    load_dotenv(env_file)

    api_key = os.getenv(live_cfg.api_key_env)
    api_secret = os.getenv(live_cfg.api_secret_env)
    api_passphrase = os.getenv(live_cfg.api_passphrase_env)

    if not all([api_key, api_secret, api_passphrase]):
        raise ValueError("Missing OKX API credentials in environment")

    # Convert instrument IDs to OKX format (with hyphens)
    okx_instrument_ids = [
        convert_to_exchange_format(inst_id, "OKX") for inst_id in instrument_ids
    ]
    load_ids = frozenset(okx_instrument_ids)

    data_config = OKXDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        instrument_types=(OKXInstrumentType.SWAP,),
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        contract_types=(OKXContractType.LINEAR,),
        is_demo=False,
    )

    exec_config = OKXExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        instrument_types=(OKXInstrumentType.SWAP,),
        contract_types=(OKXContractType.LINEAR,),
        is_demo=False,
    )

    return data_config, exec_config, okx_instrument_ids


def _load_configs(env_name: Optional[str]):
    """加载配置"""
    if env_name:
        return load_config(env_name)

    from core.loader import create_default_loader

    loader = create_default_loader()
    active_config = loader.load_active_config()
    env_config, strategy_config, _ = load_config(active_config.environment)
    return env_config, strategy_config, active_config


def _validate_live_config(env_config):
    """验证实盘配置"""
    if not hasattr(env_config, "live") or not env_config.live:
        raise ValueError("Environment does not have live trading configuration")


def _create_trader_id(live_cfg, active_config) -> tuple:
    """创建交易者ID"""
    trader_name = f"{live_cfg.venue}_{active_config.primary_symbol}_LIVE"
    trader_id = TraderId(trader_name.replace("_", "-"))
    return trader_name, trader_id


def _create_logging_config(env_config, trader_name):
    """创建日志配置"""
    log_dir = BASE_DIR / "log" / "live" / trader_name
    return LoggingConfig(
        log_level=env_config.logging.level,
        log_level_file=env_config.logging.file_level,
        log_directory=str(log_dir / "runtime"),
        log_colors=True,
        use_pyo3=True,
    )


def _build_venue_configs(live_cfg, instrument_ids):
    """构建交易所配置"""
    if live_cfg.venue == "BINANCE":
        data_config, exec_config = build_binance_config(live_cfg, instrument_ids)
        return {
            "data_clients": {BINANCE: data_config},
            "exec_clients": {BINANCE: exec_config},
            "data_factory": {BINANCE: BinanceLiveDataClientFactory},
            "exec_factory": {BINANCE: BinanceLiveExecClientFactory},
            "converted_ids": instrument_ids,  # Binance doesn't need conversion
        }
    elif live_cfg.venue == "OKX":
        data_config, exec_config, okx_instrument_ids = build_okx_config(live_cfg, instrument_ids)
        return {
            "data_clients": {OKX: data_config},
            "exec_clients": {OKX: exec_config},
            "data_factory": {OKX: OKXLiveDataClientFactory},
            "exec_factory": {OKX: OKXLiveExecClientFactory},
            "converted_ids": okx_instrument_ids,  # OKX uses converted IDs
        }
    else:
        raise ValueError(f"Unsupported venue: {live_cfg.venue}")


def _create_node_config(trader_id, logging_config, live_cfg, venue_configs):
    """创建节点配置"""
    return TradingNodeConfig(
        environment=Environment.LIVE,
        trader_id=trader_id,
        logging=logging_config,
        exec_engine=LiveExecEngineConfig(
            reconciliation=live_cfg.reconciliation,
            reconciliation_lookback_mins=live_cfg.reconciliation_lookback_mins,
            filter_position_reports=live_cfg.filter_position_reports,
        ),
        cache=CacheConfig(
            timestamps_as_iso8601=True,
            flush_on_start=live_cfg.flush_cache_on_start,
        ),
        data_clients=venue_configs["data_clients"],
        exec_clients=venue_configs["exec_clients"],
        timeout_connection=10.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )


def _setup_node(node, strategy_config, instrument_ids, venue_configs):
    """设置节点"""
    strategy = load_strategy_instance(strategy_config, instrument_ids)
    node.trader.add_strategy(strategy)

    for venue, factory in venue_configs["data_factory"].items():
        node.add_data_client_factory(venue, factory)
    for venue, factory in venue_configs["exec_factory"].items():
        node.add_exec_client_factory(venue, factory)

    node.build()


def _load_instruments(node, instrument_ids):
    """加载标的信息"""
    for inst_id_str in instrument_ids:
        venue_str = inst_id_str.split(".")[-1]
        inst_file = (
            BASE_DIR / "data" / "instrument" / venue_str / f"{inst_id_str.split('.')[0]}.json"
        )

        if inst_file.exists():
            inst = load_instrument(inst_file)
            node.cache.add_instrument(inst)


async def run_live(env_name: Optional[str] = None):
    """运行实盘交易"""
    env_config, strategy_config, active_config = _load_configs(env_name)
    _validate_live_config(env_config)

    live_cfg = env_config.live
    trader_name, trader_id = _create_trader_id(live_cfg, active_config)
    logging_config = _create_logging_config(env_config, trader_name)

    instrument_ids = live_cfg.instrument_ids
    venue_configs = _build_venue_configs(live_cfg, instrument_ids)

    # Use converted IDs for strategy and instrument loading
    converted_ids = venue_configs["converted_ids"]

    node_config = _create_node_config(trader_id, logging_config, live_cfg, venue_configs)
    node = TradingNode(config=node_config)

    _setup_node(node, strategy_config, converted_ids, venue_configs)
    _load_instruments(node, converted_ids)

    try:
        await node.run_async()
    finally:
        await node.stop_async()
        await asyncio.sleep(1)
        node.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Unified Live Trading Runner")
    parser.add_argument("--env", type=str, help="Environment name (default: from active.yaml)")
    args = parser.parse_args()

    asyncio.run(run_live(args.env))
