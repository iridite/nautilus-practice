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
from utils.instrument_loader import load_instrument


def load_strategy_instance(strategy_config, instrument_ids):
    """动态加载策略实例"""
    module_path = strategy_config.module_path
    strategy_name = strategy_config.name
    config_class_name = strategy_config.config_class or f"{strategy_name}Config"

    module = __import__(module_path, fromlist=[strategy_name, config_class_name])
    StrategyClass = getattr(module, strategy_name)
    ConfigClass = getattr(module, config_class_name)

    params = strategy_config.parameters.copy()

    if len(instrument_ids) == 1:
        params["instrument_id"] = instrument_ids[0]
    else:
        raise ValueError(f"Live trading currently only supports single instrument, got {len(instrument_ids)}")

    if "btc_symbol" in params and (not params.get("btc_instrument_id") or params.get("btc_instrument_id") == ""):
        inst_id = params["instrument_id"]
        parts = inst_id.split(".")
        venue = parts[-1]
        symbol_parts = parts[0].split("-")
        inst_type = symbol_parts[-1] if len(symbol_parts) > 2 else "PERP"

        btc_symbol = params["btc_symbol"]
        if "USDT" in btc_symbol:
            base = btc_symbol.replace("USDT", "")
            formatted_symbol = f"{base}-USDT"
        else:
            formatted_symbol = btc_symbol

        params["btc_instrument_id"] = f"{formatted_symbol}-{inst_type}.{venue}"

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

    load_ids = frozenset(instrument_ids)

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

    return data_config, exec_config


async def run_live(env_name: Optional[str] = None):
    """运行实盘交易"""
    if env_name:
        env_config, strategy_config, active_config = load_config(env_name)
    else:
        from core.loader import create_default_loader
        loader = create_default_loader()
        active_config = loader.load_active_config()
        env_config, strategy_config, _ = load_config(active_config.environment)

    if not hasattr(env_config, 'live') or not env_config.live:
        raise ValueError("Environment does not have live trading configuration")

    live_cfg = env_config.live

    trader_name = f"{live_cfg.venue}_{active_config.primary_symbol}_LIVE"
    trader_id = TraderId(trader_name.replace("_", "-"))

    log_dir = BASE_DIR / "log" / "live" / trader_name
    logging_config = LoggingConfig(
        log_level=env_config.logging.level,
        log_level_file=env_config.logging.file_level,
        log_directory=str(log_dir / "runtime"),
        log_colors=True,
        use_pyo3=True,
    )

    instrument_ids = live_cfg.instrument_ids

    if live_cfg.venue == "BINANCE":
        data_config, exec_config = build_binance_config(live_cfg, instrument_ids)
        data_clients = {BINANCE: data_config}
        exec_clients = {BINANCE: exec_config}
        data_factory = {BINANCE: BinanceLiveDataClientFactory}
        exec_factory = {BINANCE: BinanceLiveExecClientFactory}
    elif live_cfg.venue == "OKX":
        data_config, exec_config = build_okx_config(live_cfg, instrument_ids)
        data_clients = {OKX: data_config}
        exec_clients = {OKX: exec_config}
        data_factory = {OKX: OKXLiveDataClientFactory}
        exec_factory = {OKX: OKXLiveExecClientFactory}
    else:
        raise ValueError(f"Unsupported venue: {live_cfg.venue}")

    node_config = TradingNodeConfig(
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
        data_clients=data_clients,
        exec_clients=exec_clients,
        timeout_connection=10.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )

    node = TradingNode(config=node_config)

    strategy = load_strategy_instance(strategy_config, instrument_ids)
    node.trader.add_strategy(strategy)

    for venue, factory in data_factory.items():
        node.add_data_client_factory(venue, factory)
    for venue, factory in exec_factory.items():
        node.add_exec_client_factory(venue, factory)

    node.build()

    for inst_id_str in instrument_ids:
        venue_str = inst_id_str.split(".")[-1]
        inst_file = BASE_DIR / "data" / "instrument" / venue_str / f"{inst_id_str.split('.')[0]}.json"

        if inst_file.exists():
            inst = load_instrument(inst_file)
            node.cache.add_instrument(inst)

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
