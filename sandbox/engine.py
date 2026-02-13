"""
统一的Sandbox运行框架

基于YAML配置文件快速启动实时交易环境
"""

import asyncio
import copy
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

import logging

logger = logging.getLogger(__name__)

from core.loader import load_config
from core.schemas import SandboxConfig
from sandbox.preflight import run_preflight
from utils.instrument_helpers import build_bar_type_from_timeframe, format_aux_instrument_id
from utils.instrument_loader import load_instrument


def load_strategy_instances(strategy_config, instrument_ids):
    """动态加载策略实例列表 (支持多标的)"""
    # 硬限制：防止创建过多策略实例导致性能问题
    MAX_STRATEGY_INSTANCES = 20

    if len(instrument_ids) > MAX_STRATEGY_INSTANCES:
        raise ValueError(
            f"Too many instrument_ids ({len(instrument_ids)}). "
            f"Maximum allowed: {MAX_STRATEGY_INSTANCES}.\n"
            f"This limit prevents performance issues from excessive strategy instances.\n"
            f"Consider:\n"
            f"  1. Using a smaller universe (reduce universe_top_n)\n"
            f"  2. Filtering symbols in strategy config\n"
            f"  3. Running multiple sandbox instances with different symbol groups"
        )

    module_path = strategy_config.module_path
    strategy_name = strategy_config.name
    config_class_name = strategy_config.config_class or f"{strategy_name}Config"

    # 动态导入策略模块
    module = __import__(module_path, fromlist=[strategy_name, config_class_name])
    StrategyClass = getattr(module, strategy_name)
    ConfigClass = getattr(module, config_class_name)

    strategies = []
    for inst_id in instrument_ids:
        # 构建策略配置 - 使用深拷贝避免多个策略实例共享可变对象
        params = copy.deepcopy(strategy_config.parameters)
        params["instrument_id"] = inst_id

        # 构建 bar_type (必须提供给策略，否则 on_start 会失败)
        if not params.get("bar_type"):
            params["bar_type"] = build_bar_type_from_timeframe(
                instrument_id=inst_id,
                timeframe=params.get("timeframe", "1d"),
                price_type=params.get("price_type", "LAST"),
                origination=params.get("origination", "EXTERNAL"),
            )

        # 生成唯一的 StrategyId - 包含venue避免冲突
        venue_part = inst_id.split(".")[-1]
        symbol_part = inst_id.split(".")[0]
        params["strategy_id"] = f"{strategy_name}-{symbol_part}-{venue_part}"

        # 处理 btc_instrument_id（如果策略需要）
        if "btc_symbol" in params and (not params.get("btc_instrument_id") or params.get("btc_instrument_id") == ""):
            try:
                # Prefer deriving the BTC instrument by inheriting contract type and venue
                params["btc_instrument_id"] = format_aux_instrument_id(params["btc_symbol"], template_inst_id=inst_id)
            except Exception as e:
                logger.exception("Failed to format btc_instrument_id for template %s, btc_symbol=%s: %s", inst_id, params.get("btc_symbol"), e)
                raise

        # 过滤掉配置类中不存在的参数（如 YAML 中的 symbols）
        # 优先使用 Pydantic 的 model_fields（如果是 Pydantic 模型）
        valid_fields = set()
        if hasattr(ConfigClass, 'model_fields'):
            # Pydantic v2 模型
            valid_fields = set(ConfigClass.model_fields.keys())
        elif hasattr(ConfigClass, '__fields__'):
            # Pydantic v1 模型
            valid_fields = set(ConfigClass.__fields__.keys())
        else:
            # 回退到 __annotations__（dataclass 或普通类）
            for cls_ in ConfigClass.__mro__:
                valid_fields.update(getattr(cls_, "__annotations__", {}).keys())

        # 过滤参数并记录被过滤的参数
        valid_params = {k: v for k, v in params.items() if k in valid_fields}
        filtered_params = {k: v for k, v in params.items() if k not in valid_fields}

        if filtered_params:
            logger.debug(
                "Filtered out unknown parameters for %s: %s",
                ConfigClass.__name__,
                list(filtered_params.keys())
            )

        config = ConfigClass(**valid_params)
        strategies.append(StrategyClass(config=config))

    return strategies


def build_okx_config(sandbox_cfg: SandboxConfig, instrument_ids):
    """构建OKX配置"""
    # 根据 testnet 模式选择环境变量文件
    if sandbox_cfg.is_testnet:
        env_file = BASE_DIR / "test.env"
        if not env_file.exists():
            logger.error("Testnet environment file not found: %s", env_file)
            raise FileNotFoundError(
                f"Testnet environment file not found: {env_file}\n"
                f"Please create test.env with OKX testnet API credentials"
            )
    else:
        env_file = BASE_DIR / ".env"
        if not env_file.exists():
            logger.error("Environment file not found: %s", env_file)
            raise FileNotFoundError(f"Environment file not found: {env_file}")

    load_dotenv(env_file)

    api_key = os.getenv(sandbox_cfg.api_key_env)
    api_secret = os.getenv(sandbox_cfg.api_secret_env)
    api_passphrase = os.getenv(sandbox_cfg.api_passphrase_env)

    if not all([api_key, api_secret, api_passphrase]):
        logger.error(
            "Missing API credentials in environment. Needed env vars: %s, %s, %s",
            sandbox_cfg.api_key_env,
            sandbox_cfg.api_secret_env,
            sandbox_cfg.api_passphrase_env,
        )
        raise ValueError("Missing API credentials in environment")

    # 验证API凭证格式和长度
    if len(api_key) < 10:
        raise ValueError(
            f"API key appears to be invalid (too short: {len(api_key)} chars). "
            f"Expected at least 10 characters."
        )

    if len(api_secret) < 10:
        raise ValueError(
            f"API secret appears to be invalid (too short: {len(api_secret)} chars). "
            f"Expected at least 10 characters."
        )

    if len(api_passphrase) < 1:
        raise ValueError("API passphrase cannot be empty")

    logger.info(
        "API credentials loaded: key=%s..., secret=%s..., passphrase=***",
        api_key[:8] if len(api_key) >= 8 else "***",
        api_secret[:8] if len(api_secret) >= 8 else "***"
    )

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

    # 生产环境安全检查：禁止在生产模式下使用 allow_missing_instruments
    if not sandbox_cfg.is_testnet and sandbox_cfg.allow_missing_instruments:
        raise ValueError(
            "Security violation: allow_missing_instruments=True is not allowed in production mode.\n"
            "This setting bypasses critical safety checks and could lead to runtime failures.\n"
            "Please either:\n"
            "  1. Set is_testnet=true (for sandbox/testing)\n"
            "  2. Set allow_missing_instruments=false (for production)\n"
            "  3. Ensure all instrument files are present before starting"
        )

    # Run preflight checks to catch common startup issues early.
    try:
        # Allow sandbox config to opt-in to treating missing instrument json files
        # as non-blocking warnings by setting `allow_missing_instruments: true`.
        warn_missing = bool(getattr(sandbox_cfg, "allow_missing_instruments", False))
        problems = run_preflight(
            BASE_DIR,
            sandbox_cfg,
            strategy_config,
            warn_on_missing_instruments=warn_missing,
        )
    except Exception as e:
        logger.exception("Preflight execution failed with an unexpected error: %s", e)
        raise

    if problems:
        for p in problems:
            logger.error("Preflight problem: %s", p)
        # Fail fast: do not attempt to start sandbox when preflight detects issues.
        raise RuntimeError("Preflight checks failed; see logs for details.")

    # 构建交易者名称和日志目录
    # 使用时间戳确保唯一性，避免多标的场景下的命名混淆
    from datetime import datetime
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    mode = 'TESTNET' if sandbox_cfg.is_testnet else 'LIVE'
    trader_name = f"{sandbox_cfg.venue}_{mode}_{timestamp}"
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
        btc_symbol = strategy_config.parameters["btc_symbol"]

        # 验证是否有模板标的
        if not instrument_ids:
            raise ValueError(
                f"Cannot derive BTC instrument_id: no template instrument_ids provided. "
                f"Please add at least one instrument_id to sandbox.yaml"
            )

        # Use the first instrument as a template to inherit contract type and venue
        inst_id = instrument_ids[0]
        try:
            aux_id = format_aux_instrument_id(btc_symbol, template_inst_id=inst_id)
            all_needed_ids.add(aux_id)
            logger.info(
                "Derived auxiliary instrument id: %s (from template: %s, btc_symbol: %s)",
                aux_id, inst_id, btc_symbol
            )
        except Exception as e:
            # BTC标的对于策略至关重要，必须抛出异常
            raise RuntimeError(
                f"Failed to derive BTC instrument_id from template {inst_id}: {e}\n"
                f"btc_symbol: {btc_symbol}\n"
                f"Please either:\n"
                f"  1. Fix the btc_symbol format in strategy config\n"
                f"  2. Manually add BTC instrument_id to sandbox.yaml\n"
                f"  3. Disable BTC market regime filter in strategy config"
            ) from e

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
        data_clients=data_clients,  # type: ignore[arg-type]
        exec_clients=exec_clients,  # type: ignore[arg-type]
        # 使用配置化的超时参数
        timeout_connection=sandbox_cfg.timeout_connection,
        timeout_reconciliation=sandbox_cfg.timeout_reconciliation,
        timeout_portfolio=sandbox_cfg.timeout_portfolio,
        timeout_disconnection=sandbox_cfg.timeout_disconnection,
        timeout_post_stop=sandbox_cfg.timeout_post_stop,
    )

    # 创建节点 - 使用try-finally确保资源清理
    node = None
    try:
        node = TradingNode(config=node_config)

        # 注册客户端工厂
        for venue, factory in data_factory.items():
            node.add_data_client_factory(venue, factory)
        for venue, factory in exec_factory.items():
            node.add_exec_client_factory(venue, factory)

        node.build()

        # 加载本地标的文件 (包含辅助标地)
        missing_instruments = []
        loaded_instruments = []

        for inst_id_str in all_needed_ids:
            venue_str = inst_id_str.split(".")[-1]
            inst_file = BASE_DIR / "data" / "instrument" / venue_str / f"{inst_id_str.split('.')[0]}.json"

            if inst_file.exists():
                inst = load_instrument(inst_file)
                node.cache.add_instrument(inst)
                loaded_instruments.append(inst_id_str)
            else:
                missing_instruments.append((inst_id_str, inst_file))
                logger.warning(
                    "Instrument file not found: %s (instrument id: %s)",
                    inst_file,
                    inst_id_str,
                )

        # 检查缺失的标的文件
        if missing_instruments:
            if not sandbox_cfg.allow_missing_instruments:
                missing_list = "\n".join([f"  - {inst_id} (expected: {path})" for inst_id, path in missing_instruments])
                raise FileNotFoundError(
                    f"Missing instrument files for {len(missing_instruments)} instrument(s):\n{missing_list}\n\n"
                    f"Solutions:\n"
                    f"  1. Run: uv run python scripts/fetch_instrument.py\n"
                    f"  2. Or set 'allow_missing_instruments: true' in sandbox.yaml (not recommended for production)"
                )
            else:
                logger.warning(
                    "Continuing with %d missing instrument(s) (allow_missing_instruments=true)",
                    len(missing_instruments)
                )

        # 只为已加载标的创建策略实例
        valid_instrument_ids = [inst_id for inst_id in instrument_ids if inst_id in loaded_instruments]

        if not valid_instrument_ids:
            raise RuntimeError(
                "No valid instruments available to create strategies. "
                "All instrument files are missing."
            )

        if len(valid_instrument_ids) < len(instrument_ids):
            skipped = set(instrument_ids) - set(valid_instrument_ids)
            logger.warning(
                "Skipping %d instrument(s) due to missing files: %s",
                len(skipped),
                ", ".join(skipped)
            )

        # 加载策略实例（仅为有效标的）
        strategies = load_strategy_instances(strategy_config, valid_instrument_ids)
        logger.info("Loaded %d strategy instance(s) from config %s", len(strategies), getattr(strategy_config, "name", "unknown"))
        for strategy in strategies:
            node.trader.add_strategy(strategy)
            sid = getattr(getattr(strategy, "config", None), "strategy_id", None)
            logger.info("Registered strategy instance: %s", sid or repr(strategy))

        # 运行节点
        await node.run_async()

    finally:
        # 确保节点资源被正确清理
        if node is not None:
            try:
                logger.info("Stopping trading node...")
                await node.stop_async()
                await asyncio.sleep(1)
                node.dispose()
                logger.info("Trading node stopped and disposed successfully")
            except Exception as cleanup_error:
                logger.error(f"Error during node cleanup: {cleanup_error}", exc_info=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Unified Sandbox Runner")
    parser.add_argument("--env", type=str, help="Environment name (default: from active.yaml)")
    args = parser.parse_args()

    asyncio.run(run_sandbox(args.env))
