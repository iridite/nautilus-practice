"""
Universe 配置解析模块

提供 Universe 文件加载、符号提取和解析功能。
"""

import json
from pathlib import Path
from typing import Dict, List, Set, Union

from core.exceptions import UniverseParseError
from core.schemas import InstrumentConfig, InstrumentType


import logging
logger = logging.getLogger(__name__)

def load_universe_file(universe_path: Union[str, Path]) -> Dict[str, List[str]]:
    """
    加载 Universe JSON 文件

    Parameters
    ----------
    universe_path : Union[str, Path]
        Universe 文件路径

    Returns
    -------
    Dict[str, List[str]]
        Universe 数据字典，键为月份，值为符号列表

    Raises
    ------
    UniverseParseError
        文件不存在、格式错误或解析失败
    """
    universe_path = Path(universe_path)

    if not universe_path.exists():
        raise UniverseParseError(f"Universe file not found: {universe_path}")

    if universe_path.suffix.lower() != ".json":
        raise UniverseParseError(f"Universe file must be JSON format: {universe_path}")

    try:
        with open(universe_path, "r", encoding="utf-8") as f:
            universe_data = json.load(f)

        if not isinstance(universe_data, dict):
            raise UniverseParseError(f"Universe file must contain a JSON object: {universe_path}")

        for month, symbols in universe_data.items():
            if not isinstance(symbols, list):
                raise UniverseParseError(f"Month '{month}' must contain a list of symbols")

        return universe_data

    except json.JSONDecodeError as e:
        raise UniverseParseError(f"Invalid JSON format in {universe_path}: {e}")
    except Exception as e:
        raise UniverseParseError(f"Error loading universe file {universe_path}: {e}")


def extract_universe_symbols(
    universe_data: Dict[str, List[str]],
    months: List[str] | None = None
) -> Set[str]:
    """
    从 Universe 数据中提取符号集合

    Parameters
    ----------
    universe_data : Dict[str, List[str]]
        Universe 数据字典
    months : List[str] | None, optional
        要提取的月份列表，None 表示提取所有月份

    Returns
    -------
    Set[str]
        符号集合
    """
    if months is None:
        months = list(universe_data.keys())

    symbols = set()
    for month in months:
        if month in universe_data:
            symbols.update(universe_data[month])
        else:
            logger.warning(f"⚠️ Month '{month}' not found in universe data")

    return symbols


def load_universe_symbols_from_file(file_path: Union[str, Path]) -> List[str]:
    """
    从文本文件加载 Universe 符号列表

    支持简单文本格式，每行一个符号，支持注释和空行。

    Parameters
    ----------
    file_path : Union[str, Path]
        Universe 文件路径

    Returns
    -------
    List[str]
        符号列表，保持顺序并去重
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.warning(f"⚠️ Universe file not found: {file_path}")
        return []

    try:
        symbols = []
        seen = set()

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '#' in line:
                    line = line[:line.index('#')]
                line = line.strip()

                if not line:
                    continue

                symbol = line.upper()
                if symbol not in seen:
                    symbols.append(symbol)
                    seen.add(symbol)

        return symbols

    except Exception as e:
        logger.error(f"⚠️ Error reading universe file {file_path}: {e}")
        return []


def parse_universe_symbols(
    universe_symbols: Set[str],
    venue: str,
    base_currency: str,
    inst_type: InstrumentType
) -> Set[str]:
    """
    将 Universe 符号转换为 Instrument ID

    Parameters
    ----------
    universe_symbols : Set[str]
        Universe 符号集合
    venue : str
        交易所名称
    base_currency : str
        基准货币
    inst_type : InstrumentType
        标的类型

    Returns
    -------
    Set[str]
        Instrument ID 集合
    """
    instrument_ids = set()

    for symbol in universe_symbols:
        try:
            raw_pair = symbol.split(":")[0]

            if not raw_pair.endswith(base_currency):
                logger.warning(f"⚠️ Symbol '{symbol}' doesn't end with base currency '{base_currency}'")
                continue

            quote_currency = raw_pair.replace(base_currency, "")

            if not quote_currency:
                logger.warning(f"⚠️ Empty quote currency for symbol '{symbol}'")
                continue

            inst_id = InstrumentConfig.get_id_for(
                venue_name=venue,
                base_currency=base_currency,
                quote_currency=quote_currency,
                inst_type=inst_type,
            )
            instrument_ids.add(inst_id)

        except Exception as e:
            logger.error(f"⚠️ Failed to parse symbol '{symbol}': {e}")
            continue

    return instrument_ids


def resolve_universe_path(
    universe_name: str | None,
    base_dir: Union[str, Path]
) -> Path | None:
    """
    解析 universe 文件的完整路径

    Parameters
    ----------
    universe_name : str | None
        Universe 文件名或路径
    base_dir : Union[str, Path]
        项目基础目录

    Returns
    -------
    Path | None
        解析后的完整路径，如果文件不存在返回 None
    """
    if not universe_name:
        return None

    # 如果是绝对路径，直接使用
    if Path(universe_name).is_absolute():
        universe_path = Path(universe_name)
    else:
        # 相对路径，在data目录下查找
        universe_path = Path(base_dir) / "data" / Path(universe_name).name

    if universe_path.exists():
        return universe_path
    else:
        return None
