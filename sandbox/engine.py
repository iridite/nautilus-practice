"""
统一的Sandbox运行框架

基于YAML配置文件快速启动实时交易环境
"""

import asyncio
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from nautilus_trader.adapters.okx import OKX, OKXDataClientConfig, OKXExecClientConfig
from nautilus_trader.adapters.okx.factories import (
    OKXLiveDataClientFactory,
    OKXLiveExecClientFactory,
)
from nautilus_trader.config import (
    CacheConfig,
    InstrumentProviderConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.core.nautilus_pyo3 import OKXContractType, OKXInstrumentType
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId, TraderId

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from config.loader import load_config
from config.schemas import SandboxConfig
from utils.instrument_loader import load_instrument


def load_strategy_instance(strategy_config, env_config, instrument_ids):
    """动态加载策略实例"""
    module_path = strategy_config.module_path
    strategy_name = strategy_config.name
    config_class_name = strategy_config.config_class or f"{strategy_name}Config"

    # 动态导入策略模块
    module = __import__(module_path, fromlist=[strategy_name, config_class_name])
    StrategyClass = getattr(module, strategy_name)
    ConfigClass = getattr(module, config_class_name)

    # 构建策略配置
    params = strategy_config.parameters.copy()

    # 注入必要参数
    if len(instrument_ids) == 1:
        params["instrument_id"] = instrument_ids[0]

    config = ConfigClass(**params)
    return StrategyClass(config=config)


def build_okx_config(sandbox_cfg: SandboxConfig, env_config, instrument_ids):
    """构建OKX配置"""
    # 加载环境变量
    env_file = BASE_DIR / ("test.env" if sandbox_cfg.is_testnet else ".env")
    load_dotenv(env_file)

    api_key = os.getenv(sandbox_cfg.api_key_env)
    api_secret = os.getenv(sandbox_cfg.api_secret_env)
    api_passphrase = os.getenv(sandbox_cfg.api_passphrase_env)

    if not all([api_key, api_secret, api_passphrase]):
        raise ValueError("Missing API credentials in environment")

    # 转换instrument_ids为frozenset
    load_ids = frozenset(instrument_ids)

    # 数据客户端配置
    data_config = OKXDataClientConfig(
        base_url_ws="wss://wspap.okx.com:8443/ws/v5/public" if sandbox_cfg.is_testnet else None,
        instrument_types=(OKXInstrumentType.SWAP,),
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        contract_types=(OKXContractType.LINEAR,),
        is_demo=sandbox_cfg.is_testnet,
    )

    # 执行客户端配置
    exec_config = OKXExecClientConfig(
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        instrument_types=(OKXInstrumentType.SWAP,),
        contract_types=(OKXContractType.LINEAR,),
        is_demo=sandbox_cfg.is_testnet,
    )

    return data_config, exec_config


async def run_sandbox(env_name: str = None):
    """运行Sandbox"""
    # 加载配置
    env_config, strategy_config, active_config = load_config(env_name or active_config.environment)

    if not env_config.sandbox:
        raise ValueError(f"Environment '{env_name}' does not have sandbox configuration")

    sandbox_cfg = env_config.sandbox

    # 构建trader_id
    trader_name = f"{sandbox_cfg.venue}_{active_config.primary_symbol}_{'TESTNET' if sandbox_cfg.is_testnet else 'LIVE'}"
    trader_id = TraderId(trader_name.replace("_", "-"))

    # 日志配置
    log_dir = BASE_DIR / "log" / "sandbox" / trader_name
    logging_config = LoggingConfig(
        log_level=env_config.logging.level,
        log_level_file=env_config.logging.file_level,
        log_directory=str(log_dir / "runtime"),
        log_colors=True,
        use_pyo3=True,
    )

    # 构建交易所配置
    instrument_ids = sandbox_cfg.instrument_ids

    if sandbox_cfg.venue == "OKX":
        data_config, exec_config = build_okx_config(sandbox_cfg, env_config, instrument_ids)
        data_clients = {OKX: data_config}
        exec_clients = {OKX: exec_config}
        data_factory = {OKX: OKXLiveDataClientFactory}
        exec_factory = {OKX: OKXLiveExecClientFactory}
    else:
        raise ValueError(f"Unsupported venue: {sandbox_cfg.venue}")

    # 构建节点配置
    node_config = TradingNodeConfig(
        trader_id=trader_id,
        logging=logging_config,
        exec_engine=LiveExecEngineConfig(
            reconciliation=sandbox_cfg.reconciliation,
            reconciliation_lookback_mins=sandbox_cfg.reconciliation_lookback_mins,
            filter_position_reports=sandbox_cfg.filter_position_reports,
        ),
        cache=CacheConfig(
            timestamps_as_iso8601=True,
            flush_on_start=sandbox_cfg.flush_cache_on_start,
        ),
        data_clients=data_clients,
        exec_clients=exec_clients,
        timeout_connection=10.0,
        timeout_reconciliation=10.0,
        timeout_portfolio=10.0,
        timeout_disconnection=10.0,
        timeout_post_stop=5.0,
    )

    # 创建节点
    node = TradingNode(config=node_config)

    # 加载策略
    strategy = load_strategy_instance(strategy_config, env_config, instrument_ids)
    node.trader.add_strategy(strategy)

    # 注册客户端工厂
    for venue, factory in data_factory.items():
        node.add_data_client_factory(venue, factory)
    for venue, factory in exec_factory.items():
        node.add_exec_client_factory(venue, factory)

    node.build()

    # 加载本地标的文件
    for inst_id_str in instrument_ids:
        venue_str = inst_id_str.split(".")[-1]
        inst_file = BASE_DIR / "data" / "instrument" / venue_str / f"{inst_id_str.split('.')[0]}.json"

        if inst_file.exists():
            inst = load_instrument(inst_file)
            node.trader.add_instrument(inst)

    # 运行
    try:
        await node.run_async()
    finally:
        await node.stop_async()
        await asyncio.sleep(1)
        node.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Unified Sandbox Runner")
    parser.add_argument("--env", type=str, help="Environment name (default: from active.yaml)")
    args = parser.parse_args()

    asyncio.run(run_sandbox(args.env))
