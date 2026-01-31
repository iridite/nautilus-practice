"""
配置解析工具模块

提供策略配置解析功能。

注意：Universe 相关功能已迁移至 utils.universe 模块。
"""

from pathlib import Path
from typing import Any, Dict, Set, Union

from core.exceptions import UniverseParseError
from utils.universe import (
    extract_universe_symbols,
    load_universe_file,
    resolve_universe_path,
)


def load_strategy_universe(
    strategy_params: Union[Dict, Any],
    base_dir: Union[str, Path]
) -> Set[str]:
    """
    从策略参数中加载 universe 符号集合

    Parameters
    ----------
    strategy_params : Union[Dict, Any]
        策略参数对象或字典
    base_dir : Union[str, Path]
        项目基础目录

    Returns
    -------
    Set[str]
        Universe 符号集合

    Raises
    ------
    UniverseParseError
        当 universe 文件解析失败时
    """
    # 提取 universe 文件路径
    universe_name = None
    if isinstance(strategy_params, dict):
        universe_name = strategy_params.get("universe_filename") or strategy_params.get("universe_filepath")
    elif hasattr(strategy_params, "universe_filename"):
        universe_name = strategy_params.universe_filename
    elif hasattr(strategy_params, "universe_filepath"):
        universe_name = strategy_params.universe_filepath

    if not universe_name:
        return set()

    universe_path = resolve_universe_path(universe_name, base_dir)
    if not universe_path:
        raise UniverseParseError(f"Universe file not found: {universe_name}")

    universe_data = load_universe_file(universe_path)
    return extract_universe_symbols(universe_data)
