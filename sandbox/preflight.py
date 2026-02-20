"""
Sandbox preflight checks.

Provides a small set of defensive checks that can be run before attempting to
start the sandbox runner. The functions here are deliberately lightweight and
designed to be imported and called from `sandbox/engine.py` (or run as a
standalone script for debugging).

Usage (from engine.py):
    from sandbox.preflight import run_preflight, PreflightError
    problems = run_preflight(BASE_DIR, sandbox_cfg, strategy_config)
    if problems:
        raise PreflightError(problems)

The functions return a list[str] of human-readable problem descriptions. An
empty list means "no problems found".
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from dotenv import load_dotenv

from core.exceptions import PreflightError

logger = logging.getLogger(__name__)


def find_env_file(base_dir: Path, is_testnet: bool) -> Path:
    """
    Return the expected .env/test.env path inside `base_dir`.
    """
    return base_dir / ("test.env" if is_testnet else ".env")


def check_env_file_exists(env_file: Path) -> List[str]:
    problems: List[str] = []
    if not env_file.exists():
        problems.append(f"Environment file not found: {env_file}")
    return problems


def _parse_env_file_for_keys(env_file: Path, keys: Iterable[str]) -> List[str]:
    """
    Quick static check: look for the key names in the file contents (KEY=).
    This helps detect if the file contains the variable even if it is not
    exported into the current process environment.
    """
    problems: List[str] = []
    try:
        text = env_file.read_text(encoding="utf-8")
    except Exception as e:
        problems.append(f"Failed to read env file {env_file}: {e}")
        return problems

    for k in keys:
        if f"{k}=" not in text:
            problems.append(f"Env file {env_file} does not contain key: {k}")
    return problems


def check_api_env_vars(env_file: Path, required_keys: Iterable[str]) -> List[str]:
    """
    Load the env_file into the process environment (non-destructive) and check
    that required keys are present as environment variables. We return a list
    of missing/invalid env issues.
    """
    problems: List[str] = []

    # load into the current environment (does not overwrite existing variables by default)
    load_dotenv(env_file)

    missing = [k for k in required_keys if not os.getenv(k)]
    if missing:
        # Also check whether the env file contains the keys at all
        problems.append(f"Missing environment variables in current env: {', '.join(missing)}")
        problems += _parse_env_file_for_keys(env_file, missing)

    return problems


def try_import_strategy(module_path: str, strategy_name: str, config_name: str) -> Optional[str]:
    """
    Attempt to import `module_path` and verify that `strategy_name` and
    `config_name` exist. Returns None on success, or an error message on
    failure.
    """
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        return f"Failed to import strategy module '{module_path}': {e}"

    if not hasattr(module, strategy_name):
        return f"Strategy class '{strategy_name}' not found in module '{module_path}'"

    if not hasattr(module, config_name):
        return f"Config class '{config_name}' not found in module '{module_path}'"

    return None


def derive_aux_instrument_id(btc_symbol: str, template_inst_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to derive an auxiliary instrument id (e.g. BTC) using the project's
    helpers. Returns (aux_id, error_message). If aux_id is None, error_message
    contains the failure reason.
    """
    try:
        # Import locally to avoid potential import cycles at module import time.
        from utils.instrument_helpers import format_aux_instrument_id

        aux = format_aux_instrument_id(btc_symbol, template_inst_id=template_inst_id)
        return aux, None
    except Exception as e:
        return None, f"Failed to derive auxiliary instrument id for btc_symbol={btc_symbol} from template={template_inst_id}: {e}"


def check_instrument_files(base_dir: Path, inst_ids: Iterable[str]) -> List[str]:
    """
    Ensure instrument json files exist for the requested instrument ids. The
    repository uses `data/instrument/{VENUE}/{symbol}.json`.
    """
    problems: List[str] = []
    for inst in sorted(set(inst_ids)):
        parts = inst.split(".")
        if len(parts) < 2:
            problems.append(f"Instrument id '{inst}' has unexpected format (expected 'SYMBOL.VENUE').")
            continue
        symbol = parts[0]
        venue = parts[-1]
        inst_file = base_dir / "data" / "instrument" / venue / f"{symbol}.json"
        if not inst_file.exists():
            problems.append(f"Instrument file not found: {inst_file} (instrument id: {inst})")
    return problems


def _import_config_module(module_path: str) -> Tuple[Optional[object], List[str]]:
    """导入配置模块"""
    problems: List[str] = []
    try:
        module = importlib.import_module(module_path)
        return module, problems
    except Exception as e:
        problems.append(f"Failed to import module {module_path}: {e}")
        return None, problems


def _get_config_class(module: object, config_name: str, module_path: str) -> Tuple[Optional[type], List[str]]:
    """从模块获取配置类"""
    problems: List[str] = []
    if not hasattr(module, config_name):
        problems.append(f"Config class '{config_name}' not found in module '{module_path}'")
        return None, problems
    
    return getattr(module, config_name), problems


def _collect_valid_fields(ConfigClass: type) -> set:
    """收集配置类的有效字段"""
    valid_fields = set()
    for cls_ in getattr(ConfigClass, "__mro__", ()):
        valid_fields.update(getattr(cls_, "__annotations__", {}).keys())
    return valid_fields


def _filter_parameters(parameters: dict, valid_fields: set, config_name: str) -> dict:
    """过滤参数，只保留有效字段"""
    provided = parameters or {}
    valid_params = {k: v for k, v in provided.items() if k in valid_fields}
    unknown_keys = [k for k in provided.keys() if k not in valid_fields]
    
    if unknown_keys:
        logger.debug(
            "Filtered out unknown config keys when constructing %s: %s",
            config_name,
            unknown_keys,
        )
    
    return valid_params


def _try_construct_config(ConfigClass: type, valid_params: dict, config_name: str) -> List[str]:
    """尝试构造配置实例"""
    problems: List[str] = []
    try:
        _ = ConfigClass(**valid_params)
    except Exception as e:
        problems.append(f"Failed to construct config {config_name} with provided parameters: {e}")
    return problems


def check_strategy_instantiation(module_path: str, strategy_name: str, config_name: str, parameters: dict) -> List[str]:
    """
    Try to instantiate the ConfigClass with the provided parameters. Unknown
    parameters (those not declared on the ConfigClass or its bases) are filtered
    out before construction so that we surface real validation errors from
    Pydantic / dataclass construction rather than unexpected keyword issues.

    Note: We do not instantiate the StrategyClass itself here to avoid calling
    strategy initialization logic (which may do heavy I/O or side-effects).
    """
    # 导入模块
    module, problems = _import_config_module(module_path)
    if problems:
        return problems

    # 获取配置类
    ConfigClass, problems = _get_config_class(module, config_name, module_path)
    if problems:
        return problems

    # 收集有效字段
    valid_fields = _collect_valid_fields(ConfigClass)

    # 过滤参数
    valid_params = _filter_parameters(parameters, valid_fields, config_name)

    # 尝试构造配置
    return _try_construct_config(ConfigClass, valid_params, config_name)


def _check_environment(base_dir: Path, sandbox_cfg) -> List[str]:
    """检查环境文件和API环境变量"""
    problems = []
    
    env_file = find_env_file(base_dir, getattr(sandbox_cfg, "is_testnet", False))
    problems += check_env_file_exists(env_file)
    
    required_keys = [
        getattr(sandbox_cfg, "api_key_env", "OKX_API_KEY"),
        getattr(sandbox_cfg, "api_secret_env", "OKX_API_SECRET"),
        getattr(sandbox_cfg, "api_passphrase_env", "OKX_API_PASSPHRASE"),
    ]
    required_keys = [k for k in required_keys if k]
    
    if env_file.exists() and required_keys:
        problems += check_api_env_vars(env_file, required_keys)
    
    return problems


def _check_strategy_config(strategy_cfg) -> List[str]:
    """检查策略模块和类的可导入性"""
    problems = []
    
    module_path = getattr(strategy_cfg, "module_path", "")
    strategy_name = getattr(strategy_cfg, "name", "")
    config_name = getattr(strategy_cfg, "config_class", None) or f"{strategy_name}Config"
    
    if not module_path or not strategy_name:
        problems.append("strategy configuration missing 'module_path' or 'name'.")
        return problems
    
    imp_err = try_import_strategy(module_path, strategy_name, config_name)
    if imp_err:
        problems.append(imp_err)
    else:
        params = getattr(strategy_cfg, "parameters", {})
        problems += check_strategy_instantiation(module_path, strategy_name, config_name, params)
    
    return problems


def _collect_instrument_ids(sandbox_cfg, strategy_cfg) -> tuple[set, List[str]]:
    """收集所有需要的instrument IDs"""
    problems = []
    inst_ids = list(getattr(sandbox_cfg, "instrument_ids", []) or [])
    all_needed_ids = set(inst_ids)
    
    params = getattr(strategy_cfg, "parameters", {}) or {}
    btc_symbol = params.get("btc_symbol")
    explicit_btc_id = params.get("btc_instrument_id")
    
    if btc_symbol and not explicit_btc_id and inst_ids:
        template = inst_ids[0]
        aux_id, aux_err = derive_aux_instrument_id(btc_symbol, template)
        if aux_id:
            all_needed_ids.add(aux_id)
        else:
            problems.append(aux_err or f"Unable to derive auxiliary instrument id for btc_symbol={btc_symbol}")
    
    return all_needed_ids, problems


def _check_instruments(base_dir: Path, all_needed_ids: set, sandbox_cfg, warn_on_missing: bool) -> List[str]:
    """检查instrument文件"""
    inst_problems = check_instrument_files(base_dir, all_needed_ids)
    
    effective_warn = bool(warn_on_missing or getattr(sandbox_cfg, "allow_missing_instruments", False))
    
    if inst_problems and effective_warn:
        for p in inst_problems:
            logger.warning("Preflight warning (missing instrument): %s", p)
        return []
    
    return inst_problems


def _check_venue_support(sandbox_cfg) -> List[str]:
    """检查venue支持"""
    problems = []
    venue = getattr(sandbox_cfg, "venue", None)
    
    if not venue:
        problems.append("sandbox_cfg.venue is not set")
    else:
        supported = {"OKX", "BINANCE"}
        if venue not in supported:
            problems.append(f"Unsupported sandbox venue: {venue!r}. Supported: {', '.join(sorted(supported))}")
    
    return problems


def _deduplicate_problems(problems: List[str]) -> List[str]:
    """去重问题列表"""
    unique_problems = []
    for p in problems:
        if p not in unique_problems:
            unique_problems.append(p)
    return unique_problems


def run_preflight(base_dir: Path, sandbox_cfg, strategy_cfg, warn_on_missing_instruments: bool = False) -> List[str]:
    """
    Run the set of preflight checks and return a list of problems (empty if ok).

    This function accepts an optional flag `warn_on_missing_instruments`. When
    set to True (or when the sandbox_cfg provides `allow_missing_instruments=True`),
    missing instrument json files are treated as warnings instead of blocking
    problems; they will be logged at WARNING level but not returned as preflight
    problems.

    `sandbox_cfg` is expected to provide:
      - is_testnet: bool
      - api_key_env, api_secret_env, api_passphrase_env: str
      - venue: str
      - instrument_ids: Sequence[str]
      - (optional) allow_missing_instruments: bool

    `strategy_cfg` is expected to provide:
      - module_path: str
      - name: str
      - config_class: Optional[str]
      - parameters: dict
    """
    problems: List[str] = []
    
    problems += _check_environment(base_dir, sandbox_cfg)
    problems += _check_strategy_config(strategy_cfg)
    
    all_needed_ids, id_problems = _collect_instrument_ids(sandbox_cfg, strategy_cfg)
    problems += id_problems
    
    problems += _check_instruments(base_dir, all_needed_ids, sandbox_cfg, warn_on_missing_instruments)
    problems += _check_venue_support(sandbox_cfg)
    
    return _deduplicate_problems(problems)



# Small CLI to run preflight manually for local debugging.
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Run sandbox preflight checks")
    parser.add_argument("--env", "-e", help="Environment name (optional, will try to load active config if omitted)", default=None)
    args = parser.parse_args()

    # Try to load project config if available (best-effort; failures are reported)
    try:
        from core.loader import create_default_loader, load_config

        if args.env:
            env_config, strategy_config, active_config = load_config(args.env)
            base_dir = Path(__file__).resolve().parent.parent
        else:
            loader = create_default_loader()
            active = loader.load_active_config()
            env_config, strategy_config, _ = load_config(active.environment)
            base_dir = Path(__file__).resolve().parent.parent
        sandbox_cfg = env_config.sandbox
    except Exception as e:  # pragma: no cover - best-effort CLI
        logger.exception("Failed to load project configuration automatically: %s", e)
        print("Automatic config load failed. Please run this script by importing run_preflight() from your code with sandbox_cfg and strategy_cfg.")
        sys.exit(2)

    problems = run_preflight(base_dir, sandbox_cfg, strategy_config)
    if problems:
        print("Preflight detected problems:")
        for p in problems:
            print(f" - {p}")
        raise PreflightError(problems)

    print("Preflight OK: no problems found.")
