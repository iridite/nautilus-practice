"""
统一的Sandbox运行框架

基于YAML配置文件快速启动实时交易环境

⚠️ 重要说明:
- Sandbox 模式连接到交易所的测试网/模拟盘环境
- 这不是纯本地的 Paper Trading,而是与交易所测试服务器的真实连接
- 订单会发送到交易所的测试环境,使用虚拟资金进行交易
- 如需纯本地回测,请使用 backtest 模式而非 sandbox 模式
"""

import asyncio
import copy
import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

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
from utils.api_health_check import check_api_health
from utils.instrument_helpers import build_bar_type_from_timeframe, format_aux_instrument_id
from utils.instrument_loader import load_instrument


def _validate_instrument_count(instrument_ids: list, max_instances: int = 20):
    """验证标的数量是否超过限制"""
    if len(instrument_ids) > max_instances:
        raise ValueError(
            f"Too many instrument_ids ({len(instrument_ids)}). "
            f"Maximum allowed: {max_instances}.\n"
            f"This limit prevents performance issues from excessive strategy instances.\n"
            f"Consider:\n"
            f"  1. Using a smaller universe (reduce universe_top_n)\n"
            f"  2. Filtering symbols in strategy config\n"
            f"  3. Running multiple sandbox instances with different symbol groups"
        )


def _load_strategy_classes(strategy_config):
    """动态加载策略类和配置类"""
    module_path = strategy_config.module_path
    strategy_name = strategy_config.name
    config_class_name = strategy_config.config_class or f"{strategy_name}Config"

    module = __import__(module_path, fromlist=[strategy_name, config_class_name])
    StrategyClass = getattr(module, strategy_name)
    ConfigClass = getattr(module, config_class_name)
    
    return StrategyClass, ConfigClass


def _build_strategy_params(strategy_config, inst_id: str) -> dict:
    """构建策略参数"""
    params = copy.deepcopy(strategy_config.parameters)
    params["instrument_id"] = inst_id

    # 构建 bar_type
    if not params.get("bar_type"):
        params["bar_type"] = build_bar_type_from_timeframe(
            instrument_id=inst_id,
            timeframe=params.get("timeframe", "1d"),
            price_type=params.get("price_type", "LAST"),
            origination=params.get("origination", "EXTERNAL"),
        )

    # 生成唯一的 StrategyId
    venue_part = inst_id.split(".")[-1]
    symbol_part = inst_id.split(".")[0]
    params["strategy_id"] = f"{strategy_config.name}-{symbol_part}-{venue_part}"

    return params


def _process_btc_instrument_id(params: dict, inst_id: str):
    """处理 btc_instrument_id（如果策略需要）"""
    if "btc_symbol" in params and (not params.get("btc_instrument_id") or params.get("btc_instrument_id") == ""):
        try:
            params["btc_instrument_id"] = format_aux_instrument_id(params["btc_symbol"], template_inst_id=inst_id)
        except Exception as e:
            logger.exception("Failed to format btc_instrument_id for template %s, btc_symbol=%s: %s", inst_id, params.get("btc_symbol"), e)
            raise


def _get_valid_config_fields(ConfigClass) -> set:
    """获取配置类的有效字段"""
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
    return valid_fields


def _filter_strategy_params(params: dict, ConfigClass) -> dict:
    """过滤策略参数，只保留配置类中存在的字段"""
    valid_fields = _get_valid_config_fields(ConfigClass)
    valid_params = {k: v for k, v in params.items() if k in valid_fields}
    filtered_params = {k: v for k, v in params.items() if k not in valid_fields}

    if filtered_params:
        logger.debug(
            "Filtered out unknown parameters for %s: %s",
            ConfigClass.__name__,
            list(filtered_params.keys())
        )

    return valid_params


def _create_strategy_instance(StrategyClass, ConfigClass, params: dict):
    """创建策略实例"""
    valid_params = _filter_strategy_params(params, ConfigClass)
    config = ConfigClass(**valid_params)
    return StrategyClass(config=config)


def load_strategy_instances(strategy_config, instrument_ids):
    """动态加载策略实例列表 (支持多标的)"""
    # 硬限制：防止创建过多策略实例导致性能问题
    MAX_STRATEGY_INSTANCES = 20
    
    _validate_instrument_count(instrument_ids, MAX_STRATEGY_INSTANCES)
    
    # 动态导入策略模块
    StrategyClass, ConfigClass = _load_strategy_classes(strategy_config)

    strategies = []
    for inst_id in instrument_ids:
        # 构建策略配置
        params = _build_strategy_params(strategy_config, inst_id)
        
        # 处理 btc_instrument_id
        _process_btc_instrument_id(params, inst_id)
        
        # 创建策略实例
        strategy = _create_strategy_instance(StrategyClass, ConfigClass, params)
        strategies.append(strategy)

    return strategies


def _get_env_file_path(is_testnet: bool) -> Path:
    """获取环境变量文件路径"""
    if is_testnet:
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
    
    return env_file


def _load_api_credentials(sandbox_cfg: SandboxConfig):
    """加载API凭证"""
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
    
    return api_key, api_secret, api_passphrase


def _validate_api_credentials(api_key: str, api_secret: str, api_passphrase: str):
    """验证API凭证格式和长度"""
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


def _build_okx_data_config(api_key: str, api_secret: str, api_passphrase: str, 
                           load_ids: frozenset, is_testnet: bool) -> OKXDataClientConfig:
    """构建OKX数据客户端配置"""
    return OKXDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        base_url_ws="wss://wspap.okx.com:8443/ws/v5/public" if is_testnet else None,
        instrument_types=(OKXInstrumentType.SWAP,),
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        contract_types=(OKXContractType.LINEAR,),
        is_demo=is_testnet,
    )


def _build_okx_exec_config(api_key: str, api_secret: str, api_passphrase: str, 
                           load_ids: frozenset, is_testnet: bool) -> OKXExecClientConfig:
    """构建OKX执行客户端配置"""
    return OKXExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        api_passphrase=api_passphrase,
        instrument_provider=InstrumentProviderConfig(
            load_all=False,
            load_ids=load_ids,
        ),
        instrument_types=(OKXInstrumentType.SWAP,),
        contract_types=(OKXContractType.LINEAR,),
        is_demo=is_testnet,
    )


def build_okx_config(sandbox_cfg: SandboxConfig, instrument_ids):
    """构建OKX配置"""
    # 获取并加载环境变量文件
    env_file = _get_env_file_path(sandbox_cfg.is_testnet)
    load_dotenv(env_file)

    # 加载API凭证
    api_key, api_secret, api_passphrase = _load_api_credentials(sandbox_cfg)

    # 验证API凭证
    _validate_api_credentials(api_key, api_secret, api_passphrase)

    # 转换instrument_ids为frozenset
    load_ids = frozenset(instrument_ids)

    # 构建数据和执行客户端配置
    data_config = _build_okx_data_config(api_key, api_secret, api_passphrase, load_ids, sandbox_cfg.is_testnet)
    exec_config = _build_okx_exec_config(api_key, api_secret, api_passphrase, load_ids, sandbox_cfg.is_testnet)

    return data_config, exec_config


def _load_environment_config(env_name: Optional[str]):
    """加载环境配置"""
    if env_name:
        return load_config(env_name)
    
    # 如果未指定环境，先加载 active 配置获取默认环境
    from core.loader import create_default_loader
    loader = create_default_loader()
    active_config = loader.load_active_config()
    env_config, strategy_config, _ = load_config(active_config.environment)
    return env_config, strategy_config, active_config


def _validate_sandbox_config(env_config):
    """验证sandbox配置"""
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

    return sandbox_cfg


async def _run_api_health_check(sandbox_cfg):
    """运行 API 健康检查"""
    logger.info("=" * 60)
    logger.info("开始 API 健康检查...")
    logger.info("=" * 60)

    # 加载环境变量
    env_file = _get_env_file_path(sandbox_cfg.is_testnet)
    load_dotenv(env_file)

    # 获取 API 凭证（用于认证测试）
    api_key = os.getenv(sandbox_cfg.api_key_env)
    api_secret = os.getenv(sandbox_cfg.api_secret_env)

    # 根据交易所选择 API 端点
    if sandbox_cfg.venue == "OKX":
        base_url = "https://www.okx.com" if not sandbox_cfg.is_testnet else "https://www.okx.com"
        # OKX 使用不同的健康检查端点
        is_healthy, summary = await _check_okx_api_health(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            is_testnet=sandbox_cfg.is_testnet
        )
    elif sandbox_cfg.venue == "BINANCE":
        base_url = "https://api.binance.com" if not sandbox_cfg.is_testnet else "https://testnet.binance.vision"
        is_healthy, summary = await check_api_health(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url
        )
    else:
        logger.warning(f"API 健康检查暂不支持交易所: {sandbox_cfg.venue}，跳过检查")
        return

    # 输出检查结果
    print(summary)

    if not is_healthy:
        raise RuntimeError(
            "API 健康检查失败，无法启动交易。\n"
            "请检查:\n"
            "  1. 网络连接是否正常\n"
            "  2. API 密钥是否正确配置\n"
            "  3. 系统时间是否同步\n"
            "  4. 交易所 API 服务是否可用"
        )

    logger.info("✓ API 健康检查通过，继续启动...")


async def _check_okx_api_health(
    base_url: str,
    api_key: Optional[str],
    api_secret: Optional[str],
    is_testnet: bool
) -> Tuple[bool, str]:
    """检查 OKX API 健康状态"""
    import httpx

    results = {}
    lines = ["\n" + "="*60]
    lines.append("OKX API 健康检查结果")
    lines.append("="*60)

    # 1. 基础连接测试
    try:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base_url}/api/v5/public/time")
            elapsed_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                results["connectivity"] = True
                lines.append(f"✓ 连接测试: 成功 ({elapsed_ms:.0f}ms)")
            else:
                results["connectivity"] = False
                lines.append(f"✗ 连接测试: HTTP {response.status_code}")
    except Exception as e:
        results["connectivity"] = False
        lines.append(f"✗ 连接测试: {type(e).__name__}: {str(e)}")

    if not results.get("connectivity"):
        lines.append("="*60)
        lines.append("✗ 连接失败，无法继续检查")
        lines.append("="*60 + "\n")
        return False, "\n".join(lines)

    # 2. 时间同步检查
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            local_time = int(time.time() * 1000)
            response = await client.get(f"{base_url}/api/v5/public/time")

            if response.status_code == 200:
                server_time = int(response.json()["data"][0]["ts"])
                time_diff = abs(server_time - local_time)

                if time_diff > 5000:
                    results["time_sync"] = False
                    lines.append(f"✗ 时间同步: 时间差过大 {time_diff}ms（建议 <1000ms）")
                elif time_diff > 1000:
                    results["time_sync"] = True
                    lines.append(f"⚠ 时间同步: 时间差较大 {time_diff}ms（建议 <1000ms）")
                else:
                    results["time_sync"] = True
                    lines.append(f"✓ 时间同步: 正常 ({time_diff}ms)")
            else:
                results["time_sync"] = False
                lines.append(f"✗ 时间同步: 无法获取服务器时间")
    except Exception as e:
        results["time_sync"] = False
        lines.append(f"✗ 时间同步: {type(e).__name__}: {str(e)}")

    # 3. API 认证测试（如果提供了密钥）
    if api_key and api_secret:
        lines.append(f"⊘ API 认证: 跳过（OKX 认证需要 passphrase，将在实际连接时验证）")
    else:
        lines.append(f"⊘ API 认证: 跳过（未配置密钥）")

    lines.append("="*60)

    is_healthy = results.get("connectivity", False) and results.get("time_sync", False)

    if is_healthy:
        lines.append("✓ 所有检查通过，可以开始交易")
    else:
        lines.append("✗ 检查未通过，请修复上述问题后重试")

    lines.append("="*60 + "\n")

    return is_healthy, "\n".join(lines)


def _run_preflight_checks(sandbox_cfg, strategy_config):
    """运行预检查"""
    try:
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
        raise RuntimeError("Preflight checks failed; see logs for details.")


def _build_trader_config(sandbox_cfg, env_config):
    """构建交易者配置"""
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
    
    return trader_id, logging_config


def _derive_btc_instrument_id(btc_symbol: str, template_inst_id: str) -> str:
    """推导BTC标的ID"""
    try:
        aux_id = format_aux_instrument_id(btc_symbol, template_inst_id=template_inst_id)
        logger.info(
            "Derived auxiliary instrument id: %s (from template: %s, btc_symbol: %s)",
            aux_id, template_inst_id, btc_symbol
        )
        return aux_id
    except Exception as e:
        raise RuntimeError(
            f"Failed to derive BTC instrument_id from template {template_inst_id}: {e}\n"
            f"btc_symbol: {btc_symbol}\n"
            f"Please either:\n"
            f"  1. Fix the btc_symbol format in strategy config\n"
            f"  2. Manually add BTC instrument_id to sandbox.yaml\n"
            f"  3. Disable BTC market regime filter in strategy config"
        ) from e


def _collect_all_instrument_ids(sandbox_cfg, strategy_config):
    """收集所有需要的标的ID（包括辅助标的）"""
    instrument_ids = sandbox_cfg.instrument_ids
    all_needed_ids = set(instrument_ids)
    
    # 自动探测策略需要的辅助标的（如 BTC）
    if "btc_symbol" in strategy_config.parameters:
        btc_symbol = strategy_config.parameters["btc_symbol"]
        
        if not instrument_ids:
            raise ValueError(
                "Cannot derive BTC instrument_id: no template instrument_ids provided. "
                "Please add at least one instrument_id to sandbox.yaml"
            )
        
        aux_id = _derive_btc_instrument_id(btc_symbol, instrument_ids[0])
        all_needed_ids.add(aux_id)
    
    return list(all_needed_ids)


def _build_exchange_config(sandbox_cfg, instrument_ids):
    """构建交易所配置"""
    if sandbox_cfg.venue == "OKX":
        data_config, exec_config = build_okx_config(sandbox_cfg, instrument_ids)
        return {
            'data_clients': {OKX: data_config},
            'exec_clients': {OKX: exec_config},
            'data_factory': {OKX: OKXLiveDataClientFactory},
            'exec_factory': {OKX: OKXLiveExecClientFactory}
        }
    else:
        raise ValueError(f"Unsupported venue: {sandbox_cfg.venue}")


def _build_node_config(sandbox_cfg, trader_id, logging_config, exchange_config):
    """构建节点配置"""
    return TradingNodeConfig(
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
        data_clients=exchange_config['data_clients'],  # type: ignore[arg-type]
        exec_clients=exchange_config['exec_clients'],  # type: ignore[arg-type]
        timeout_connection=sandbox_cfg.timeout_connection,
        timeout_reconciliation=sandbox_cfg.timeout_reconciliation,
        timeout_portfolio=sandbox_cfg.timeout_portfolio,
        timeout_disconnection=sandbox_cfg.timeout_disconnection,
        timeout_post_stop=sandbox_cfg.timeout_post_stop,
    )


def _load_instrument_file(inst_id_str: str):
    """加载单个标的文件"""
    venue_str = inst_id_str.split(".")[-1]
    inst_file = BASE_DIR / "data" / "instrument" / venue_str / f"{inst_id_str.split('.')[0]}.json"
    
    if inst_file.exists():
        inst = load_instrument(inst_file)
        return inst, None
    else:
        logger.warning(
            "Instrument file not found: %s (instrument id: %s)",
            inst_file,
            inst_id_str,
        )
        return None, (inst_id_str, inst_file)


def _load_all_instruments(node, all_needed_ids):
    """加载所有标的文件"""
    missing_instruments = []
    loaded_instruments = []
    
    for inst_id_str in all_needed_ids:
        inst, missing = _load_instrument_file(inst_id_str)
        if inst:
            node.cache.add_instrument(inst)
            loaded_instruments.append(inst_id_str)
        else:
            missing_instruments.append(missing)
    
    return loaded_instruments, missing_instruments


def _validate_loaded_instruments(missing_instruments, sandbox_cfg):
    """验证加载的标的"""
    if not missing_instruments:
        return

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


def _get_valid_instrument_ids(instrument_ids, loaded_instruments):
    """获取有效的标的ID列表"""
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
    
    return valid_instrument_ids


def _load_and_register_strategies(node, strategy_config, valid_instrument_ids):
    """加载并注册策略实例"""
    strategies = load_strategy_instances(strategy_config, valid_instrument_ids)
    logger.info("Loaded %d strategy instance(s) from config %s", len(strategies), getattr(strategy_config, "name", "unknown"))
    
    for strategy in strategies:
        node.trader.add_strategy(strategy)
        sid = getattr(getattr(strategy, "config", None), "strategy_id", None)
        logger.info("Registered strategy instance: %s", sid or repr(strategy))


async def _cleanup_node(node):
    """清理节点资源"""
    if node is not None:
        try:
            logger.info("Stopping trading node...")
            await node.stop_async()
            await asyncio.sleep(1)
            node.dispose()
            logger.info("Trading node stopped and disposed successfully")
        except Exception as cleanup_error:
            logger.error(f"Error during node cleanup: {cleanup_error}", exc_info=True)


async def run_sandbox(env_name: Optional[str] = None):
    """运行Sandbox"""
    # 加载配置
    env_config, strategy_config, active_config = _load_environment_config(env_name)

    # 验证配置
    sandbox_cfg = _validate_sandbox_config(env_config)

    # API 健康检查
    await _run_api_health_check(sandbox_cfg)

    # 运行预检查
    _run_preflight_checks(sandbox_cfg, strategy_config)
    
    # 构建交易者配置
    trader_id, logging_config = _build_trader_config(sandbox_cfg, env_config)
    
    # 收集所有需要的标的ID
    all_needed_ids = _collect_all_instrument_ids(sandbox_cfg, strategy_config)
    
    # 构建交易所配置
    exchange_config = _build_exchange_config(sandbox_cfg, all_needed_ids)
    
    # 构建节点配置
    node_config = _build_node_config(sandbox_cfg, trader_id, logging_config, exchange_config)

    # 创建节点 - 使用try-finally确保资源清理
    node = None
    try:
        node = TradingNode(config=node_config)
        
        # 注册客户端工厂
        for venue, factory in exchange_config['data_factory'].items():
            node.add_data_client_factory(venue, factory)
        for venue, factory in exchange_config['exec_factory'].items():
            node.add_exec_client_factory(venue, factory)
        
        node.build()
        
        # 加载所有标的文件
        loaded_instruments, missing_instruments = _load_all_instruments(node, all_needed_ids)
        
        # 验证加载的标的
        _validate_loaded_instruments(missing_instruments, sandbox_cfg)
        
        # 获取有效的标的ID
        valid_instrument_ids = _get_valid_instrument_ids(sandbox_cfg.instrument_ids, loaded_instruments)
        
        # 加载并注册策略实例
        _load_and_register_strategies(node, strategy_config, valid_instrument_ids)
        
        # 运行节点
        await node.run_async()
    
    finally:
        await _cleanup_node(node)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Unified Sandbox Runner")
    parser.add_argument("--env", type=str, help="Environment name (default: from active.yaml)")
    args = parser.parse_args()

    asyncio.run(run_sandbox(args.env))
