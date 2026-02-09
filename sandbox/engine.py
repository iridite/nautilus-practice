"""
统一的Sandbox运行框架

基于YAML配置文件快速启动实时交易环境
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
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
from core.schemas import SandboxConfig
from utils.instrument_loader import load_instrument


def load_strategy_instances(strategy_config, instrument_ids):
    """动态加载策略实例列表 (支持多标的)"""
    module_path = strategy_config.module_path
    strategy_name = strategy_config.name
    config_class_name = strategy_config.config_class or f"{strategy_name}Config"

    # 动态导入策略模块
    module = __import__(module_path, fromlist=[strategy_name, config_class_name])
    StrategyClass = getattr(module, strategy_name)
    ConfigClass = getattr(module, config_class_name)

    strategies = []
    for inst_id in instrument_ids:
        # 构建策略配置
        params = strategy_config.parameters.copy()
        params["instrument_id"] = inst_id

        # 构建 bar_type (必须提供给策略，否则 on_start 会失败)
        if not params.get("bar_type"):
            timeframe = params.get("timeframe", "1d").lower()
            # 转换 1d -> 1-DAY, 1h -> 1-HOUR, 15m -> 15-MINUTE
            if timeframe.endswith("d"):
                period = timeframe[:-1]
                unit = "DAY"
            elif timeframe.endswith("h"):
                period = timeframe[:-1]
                unit = "HOUR"
            elif timeframe.endswith("m"):
                period = timeframe[:-1]
                unit = "MINUTE"
            else:
                period = "1"
                unit = "DAY"
            
            p_type = params.get("price_type", "LAST")
            orig = params.get("origination", "EXTERNAL")
            params["bar_type"] = f"{inst_id}-{period}-{unit}-{p_type}-{orig}"

        # 生成唯一的 StrategyId
        symbol_part = inst_id.split(".")[0]
        params["strategy_id"] = f"{strategy_name}-{symbol_part}"

        # 处理 btc_instrument_id（如果策略需要）
        if "btc_symbol" in params and (not params.get("btc_instrument_id") or params.get("btc_instrument_id") == ""):
            parts = inst_id.split(".")
            venue = parts[-1]
            symbol_parts = parts[0].split("-")
            # 保持相同的合约类型（PERP/SWAP/CASH）
            inst_type = symbol_parts[-1] if len(symbol_parts) > 2 else "PERP"

            btc_symbol = params["btc_symbol"]
            # 统一符号格式
            if "USDT" in btc_symbol and "-" not in btc_symbol:
                base = btc_symbol.replace("USDT", "")
                formatted_symbol = f"{base}-USDT"
            else:
                formatted_symbol = btc_symbol

            params["btc_instrument_id"] = f"{formatted_symbol}-{inst_type}.{venue}"

        # 过滤掉配置类中不存在的参数（如 YAML 中的 symbols）
        valid_fields = set()
        for cls_ in ConfigClass.__mro__:
            valid_fields.update(getattr(cls_, "__annotations__", {}).keys())
        
        valid_params = {k: v for k, v in params.items() if k in valid_fields}
        config = ConfigClass(**valid_params)
        strategies.append(StrategyClass(config=config))

    return strategies


def build_okx_config(sandbox_cfg: SandboxConfig, instrument_ids):
    """构建OKX配置"""
    # 根据 testnet 模式选择环境变量文件
    if sandbox_cfg.is_testnet:
        env_file = BASE_DIR / "test.env"
        if not env_file.exists():
            raise FileNotFoundError(
                f"Testnet environment file not found: {env_file}\n"
                f"Please create test.env with OKX testnet API credentials"
            )
    else:
        env_file = BASE_DIR / ".env"
        if not env_file.exists():
            raise FileNotFoundError(f"Environment file not found: {env_file}")

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
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
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
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        instrument_types=(OKXInstrumentType.SWAP,),
        contract_types=(OKXContractType.LINEAR,),
        is_demo=sandbox_cfg.is_testnet,
    )

    return data_config, exec_config


async def run_sandbox(env_name: Optional[str] = None):
    """运行Sandbox"""
    # 加载配置
    if env_name:
        env_config, strategy_config, active_config = load_config(env_name)
    else:
        # 如果未指定环境，先加载 active 配置获取默认环境
        from core.loader import create_default_loader
        loader = create_default_loader()
        active_config = loader.load_active_config()
        env_config, strategy_config, _ = load_config(active_config.environment)

    if not env_config.sandbox:
        raise ValueError("Environment does not have sandbox configuration")

    sandbox_cfg = env_config.sandbox

    # 构建针对特定标的的结算环境
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

    # 自动探测策略需要的辅助标的（如 BTC）并加入 load_ids
    all_needed_ids = set(instrument_ids)
    if "btc_symbol" in strategy_config.parameters:
        venue = sandbox_cfg.venue
        btc_symbol = strategy_config.parameters["btc_symbol"]
        # 取第一个标的来推导合约类型
        if instrument_ids:
            inst_id = instrument_ids[0]
            symbol_parts = inst_id.split(".")[0].split("-")
            inst_type = symbol_parts[-1] if len(symbol_parts) > 2 else "PERP"

            if "USDT" in btc_symbol and "-" not in btc_symbol:
                base = btc_symbol.replace("USDT", "")
                formatted_symbol = f"{base}-USDT"
            else:
                formatted_symbol = btc_symbol

            all_needed_ids.add(f"{formatted_symbol}-{inst_type}.{venue}")

    if sandbox_cfg.venue == "OKX":
        data_config, exec_config = build_okx_config(sandbox_cfg, list(all_needed_ids))
        data_clients = {OKX: data_config}
        exec_clients = {OKX: exec_config}
        data_factory = {OKX: OKXLiveDataClientFactory}
        exec_factory = {OKX: OKXLiveExecClientFactory}
    else:
        raise ValueError(f"Unsupported venue: {sandbox_cfg.venue}")

    # 构建节点配置
    node_config = TradingNodeConfig(
        environment=Environment.SANDBOX if sandbox_cfg.is_testnet else Environment.LIVE,
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

    # 注册客户端工厂
    for venue, factory in data_factory.items():
        node.add_data_client_factory(venue, factory)
    for venue, factory in exec_factory.items():
        node.add_exec_client_factory(venue, factory)

    node.build()

    # 加载本地标的文件 (包含辅助标地)
    for inst_id_str in all_needed_ids:
        venue_str = inst_id_str.split(".")[-1]
        inst_file = BASE_DIR / "data" / "instrument" / venue_str / f"{inst_id_str.split('.')[0]}.json"

        if inst_file.exists():
            inst = load_instrument(inst_file)
            node.cache.add_instrument(inst)

    # 加载策略实例
    strategies = load_strategy_instances(strategy_config, instrument_ids)
    for strategy in strategies:
        node.trader.add_strategy(strategy)

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
