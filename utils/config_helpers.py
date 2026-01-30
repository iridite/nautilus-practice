"""
配置解析工具模块

提供统一的配置文件解析、参数处理和结构验证功能。

功能包括：
- Universe 文件解析和符号提取
- 标的配置解析和ID生成
- 策略参数解析和验证
- 环境配置加载和处理
- 配置文件格式转换
- 参数默认值处理
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Union

from config.models import (
    BackTestConfig,
    DataConfig,
    InstrumentConfig,
    InstrumentType,
    LegacyStrategyConfig,
    project_root,
)


class ConfigError(Exception):
    """配置解析错误"""
    pass


class UniverseParseError(ConfigError):
    """Universe解析错误"""
    pass


class InstrumentConfigError(ConfigError):
    """标的配置错误"""
    pass


def load_universe_file(universe_path: Union[str, Path]) -> Dict[str, List[str]]:
    """
    加载 Universe 文件
    
    Parameters
    ----------
    universe_path : Union[str, Path]
        Universe 文件路径
        
    Returns
    -------
    Dict[str, List[str]]
        Universe 数据字典
        
    Raises
    ------
    UniverseParseError
        当文件加载或解析失败时
        
    Examples
    --------
    >>> universe = load_universe_file("data/universe_25.json")
    >>> print(universe.keys())  # dict_keys(['2024-01', '2024-02', ...])
    """
    universe_path = Path(universe_path)
    
    if not universe_path.exists():
        raise UniverseParseError(f"Universe file not found: {universe_path}")
    
    if not universe_path.suffix.lower() == ".json":
        raise UniverseParseError(f"Universe file must be JSON format: {universe_path}")
    
    try:
        with open(universe_path, "r", encoding="utf-8") as f:
            universe_data = json.load(f)
        
        # 验证数据格式
        if not isinstance(universe_data, dict):
            raise UniverseParseError(f"Universe file must contain a JSON object: {universe_path}")
        
        # 验证每个月份的数据都是列表
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
        要提取的月份列表，None表示提取所有月份
        
    Returns
    -------
    Set[str]
        符号集合
        
    Examples
    --------
    >>> symbols = extract_universe_symbols(universe_data)
    >>> print(len(symbols))  # 25
    
    >>> jan_symbols = extract_universe_symbols(universe_data, ["2024-01"])
    """
    if months is None:
        months = list(universe_data.keys())
    
    symbols = set()
    for month in months:
        if month in universe_data:
            symbols.update(universe_data[month])
        else:
            print(f"⚠️ Month '{month}' not found in universe data")
    
    return symbols


def load_universe_symbols_from_file(file_path: Union[str, Path]) -> List[str]:
    """
    从文本文件中解析universe符号列表
    
    支持简单文本格式的universe文件，每行一个符号，支持注释和空行。
    
    Parameters
    ----------
    file_path : Union[str, Path]
        Universe文件路径
        
    Returns
    -------
    List[str]
        符号列表，保持顺序并去重
        
    Examples
    --------
    >>> symbols = load_universe_symbols_from_file("universe.txt")
    >>> print(symbols)  # ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"⚠️ Universe file not found: {file_path}")
        return []
    
    try:
        symbols = []
        seen = set()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                # 移除注释和空白字符
                if '#' in line:
                    line = line[:line.index('#')]
                line = line.strip()
                
                # 跳过空行
                if not line:
                    continue
                
                # 转换为大写并去重
                symbol = line.upper()
                if symbol not in seen:
                    symbols.append(symbol)
                    seen.add(symbol)
        
        return symbols
        
    except Exception as e:
        print(f"⚠️ Error reading universe file {file_path}: {e}")
        return []


def parse_universe_symbols(
    universe_symbols: Set[str],
    venue: str,
    base_currency: str,
    inst_type: InstrumentType
) -> Set[str]:
    """
    从 Universe 符号列表中解析出 InstrumentID 列表
    
    Parameters
    ----------
    universe_symbols : Set[str]
        Universe 中的符号集合（如 {"SOLUSDT:USDT", "BTCUSDT:USDT", ...}）
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
        
    Examples
    --------
    >>> symbols = {"SOLUSDT:USDT", "BTCUSDT:USDT"}
    >>> ids = parse_universe_symbols(symbols, "BINANCE", "USDT", "SWAP")
    >>> print(ids)  # {"SOL-USDT-PERP.BINANCE", "BTC-USDT-PERP.BINANCE"}
    """
    instrument_ids = set()
    
    for symbol in universe_symbols:
        try:
            # 提取基础交易对：SOLUSDT:USDT -> SOLUSDT
            raw_pair = symbol.split(":")[0]
            
            # 提取 quote_currency：SOLUSDT -> SOL
            if not raw_pair.endswith(base_currency):
                print(f"⚠️ Symbol '{symbol}' doesn't end with base currency '{base_currency}'")
                continue
                
            quote_currency = raw_pair.replace(base_currency, "")
            
            if not quote_currency:
                print(f"⚠️ Empty quote currency for symbol '{symbol}'")
                continue
            
            # 使用 InstrumentConfig.get_id_for 动态生成符合交易所规范的 ID
            inst_id = InstrumentConfig.get_id_for(
                venue_name=venue,
                base_currency=base_currency,
                quote_currency=quote_currency,
                inst_type=inst_type,
            )
            instrument_ids.add(inst_id)
            
        except Exception as e:
            print(f"⚠️ Failed to parse symbol '{symbol}': {e}")
            continue
    
    return instrument_ids


def get_default_venue_and_type(
    config_instrument: Any = None,
    fallback_venue: str = "BINANCE",
    fallback_currency: str = "USDT",
    fallback_type: str = "SWAP"
) -> Tuple[str, str, str]:
    """
    获取默认的交易所和标的类型
    
    优先从配置的标的读取，如果为 None 则从全局设置或fallback值读取
    
    Parameters
    ----------
    config_instrument : Any, optional
        配置中的标的对象
    fallback_venue : str, optional
        备用交易所名称，默认 "BINANCE"
    fallback_currency : str, optional
        备用基准货币，默认 "USDT"
    fallback_type : str, optional
        备用标的类型，默认 SWAP
        
    Returns
    -------
    Tuple[str, str, str]
        (交易所名称, 基准货币, 标的类型)
        
    Examples
    --------
    >>> venue, currency, inst_type = get_default_venue_and_type()
    >>> print(venue, currency, inst_type)  # BINANCE USDT SWAP
    """
    if config_instrument:
        return (
            config_instrument.venue_name,
            config_instrument.base_currency,
            config_instrument.type,
        )
    else:
        # 多标的模式：使用fallback值或从全局设置读取
        try:
            from config.settings import VENUE, INSTRUMENT_TYPE
            return VENUE, fallback_currency, INSTRUMENT_TYPE
        except ImportError:
            return fallback_venue, fallback_currency, fallback_type


def extract_strategy_universe_path(strategy_params: Union[Dict, Any]) -> str | None:
    """
    从策略参数中提取 universe 文件路径
    
    Parameters
    ----------
    strategy_params : Union[Dict, Any]
        策略参数对象或字典
        
    Returns
    -------
    str | None
        Universe 文件路径，如果未找到返回 None
        
    Examples
    --------
    >>> path = extract_strategy_universe_path({"universe_filename": "universe_25.json"})
    >>> print(path)  # "universe_25.json"
    """
    if isinstance(strategy_params, dict):
        return (
            strategy_params.get("universe_filename") or
            strategy_params.get("universe_filepath")
        )
    else:
        return (
            getattr(strategy_params, "universe_filename", None) or
            getattr(strategy_params, "universe_filepath", None)
        )


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
        
    Examples
    --------
    >>> path = resolve_universe_path("universe_25.json", "/project")
    >>> print(path)  # /project/data/universe_25.json
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
        
    Examples
    --------
    >>> symbols = load_strategy_universe(strategy_config.params, "/project")
    >>> print(len(symbols))  # 25
    """
    universe_name = extract_strategy_universe_path(strategy_params)
    if not universe_name:
        return set()
    
    universe_path = resolve_universe_path(universe_name, base_dir)
    if not universe_path:
        raise UniverseParseError(f"Universe file not found: {universe_name}")
    
    universe_data = load_universe_file(universe_path)
    return extract_universe_symbols(universe_data)


def parse_data_feed_info(csv_file_name: str) -> Dict[str, str]:
    """
    解析数据feed配置中的CSV文件名信息
    
    Parameters
    ----------
    csv_file_name : str
        CSV文件名（格式：symbol/exchange-symbol-timeframe-date_range.csv）
        
    Returns
    -------
    Dict[str, str]
        解析出的信息字典
        
    Raises
    ------
    ConfigError
        当文件名格式不正确时
        
    Examples
    --------
    >>> info = parse_data_feed_info("BTCUSDT/binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv")
    >>> print(info)
    # {
    #     "symbol": "BTCUSDT",
    #     "exchange": "binance", 
    #     "timeframe": "1h",
    #     "start_date": "2024-01-01",
    #     "end_date": "2024-12-31"
    # }
    """
    try:
        # 分离路径和文件名：BTCUSDT/binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv
        parts = csv_file_name.split("/")
        if len(parts) != 2:
            raise ConfigError(f"Invalid CSV file name format: {csv_file_name}")
        
        symbol = parts[0]
        filename = parts[1]
        
        # 解析文件名：binance-BTCUSDT-1h-2024-01-01_2024-12-31.csv
        name_without_ext = filename.replace(".csv", "")
        file_parts = name_without_ext.split("-")
        
        if len(file_parts) < 4:
            raise ConfigError(f"Invalid file name format: {filename}")
        
        exchange = file_parts[0]
        file_symbol = file_parts[1]
        timeframe = file_parts[2]
        
        # 处理日期范围：2024-01-01_2024-12-31
        date_part = "-".join(file_parts[3:])  # 重新组合日期部分
        date_range = date_part.split("_")
        
        if len(date_range) != 2:
            raise ConfigError(f"Invalid date range format in: {filename}")
        
        return {
            "symbol": symbol,
            "file_symbol": file_symbol,
            "exchange": exchange,
            "timeframe": timeframe,
            "start_date": date_range[0],
            "end_date": date_range[1],
        }
        
    except Exception as e:
        raise ConfigError(f"Failed to parse CSV file name '{csv_file_name}': {e}")


def validate_strategy_config(config: Dict[str, Any]) -> List[str]:
    """
    验证策略配置的完整性
    
    Parameters
    ----------
    config : Dict[str, Any]
        策略配置字典
        
    Returns
    -------
    List[str]
        验证错误列表，空列表表示验证通过
        
    Examples
    --------
    >>> errors = validate_strategy_config(strategy_config)
    >>> if errors:
    ...     print("Configuration errors:", errors)
    """
    errors = []
    
    # 检查必需字段
    required_fields = ["name", "module_path"]
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    # 检查策略名称
    if "name" in config and not config["name"]:
        errors.append("Strategy name cannot be empty")
    
    # 检查模块路径
    if "module_path" in config and not config["module_path"]:
        errors.append("Module path cannot be empty")
    
    # 检查参数配置
    if "params" in config:
        params = config["params"]
        if params and isinstance(params, dict):
            # 检查关键参数的类型
            numeric_params = ["trade_size", "qty_percent", "leverage", "stop_loss_pct"]
            for param in numeric_params:
                if param in params and params[param] is not None:
                    if not isinstance(params[param], (int, float)):
                        errors.append(f"Parameter '{param}' must be numeric")
    
    return errors


def merge_config_with_defaults(
    config: Dict[str, Any],
    defaults: Dict[str, Any]
) -> Dict[str, Any]:
    """
    将配置与默认值合并
    
    Parameters
    ----------
    config : Dict[str, Any]
        用户配置
    defaults : Dict[str, Any]
        默认配置
        
    Returns
    -------
    Dict[str, Any]
        合并后的配置
        
    Examples
    --------
    >>> merged = merge_config_with_defaults(user_config, default_config)
    """
    merged = defaults.copy()
    
    def deep_merge(target: Dict, source: Dict) -> None:
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                deep_merge(target[key], value)
            else:
                target[key] = value
    
    deep_merge(merged, config)
    return merged


def normalize_symbol_format(symbol: str, target_format: str = "nautilus") -> str:
    """
    标准化符号格式
    
    Parameters
    ----------
    symbol : str
        原始符号
    target_format : str, optional
        目标格式，默认 "nautilus"
        可选值："nautilus", "ccxt", "exchange"
        
    Returns
    -------
    str
        标准化后的符号
        
    Examples
    --------
    >>> nautilus_symbol = normalize_symbol_format("BTCUSDT", "nautilus")
    >>> print(nautilus_symbol)  # "BTC/USDT:USDT"
    
    >>> ccxt_symbol = normalize_symbol_format("BTC-USDT-PERP.BINANCE", "ccxt")
    >>> print(ccxt_symbol)  # "BTC/USDT:USDT"
    """
    # 移除交易所后缀
    if "." in symbol:
        symbol = symbol.split(".")[0]
    
    # 处理不同的分隔符格式
    if "-" in symbol and not "/" in symbol:
        # BINANCE格式：BTC-USDT-PERP -> BTC/USDT:USDT
        parts = symbol.split("-")
        if len(parts) >= 2:
            base = parts[0]
            quote = parts[1]
            if target_format == "nautilus":
                return f"{base}/{quote}:{quote}"
            elif target_format == "ccxt":
                return f"{base}/{quote}:{quote}"
    
    # 已经是标准格式
    if "/" in symbol and ":" in symbol:
        return symbol
    
    # 简单格式：BTCUSDT -> BTC/USDT:USDT
    if symbol.endswith("USDT") and len(symbol) > 4:
        base = symbol[:-4]
        quote = "USDT"
        if target_format in ["nautilus", "ccxt"]:
            return f"{base}/{quote}:{quote}"
    
    return symbol


class ConfigManager:
    """
    配置管理器类
    
    提供统一的配置加载、解析和验证功能
    """
    
    def __init__(self, base_dir: Union[str, Path]):
        """
        初始化配置管理器
        
        Parameters
        ----------
        base_dir : Union[str, Path]
            项目基础目录
        """
        self.base_dir = Path(base_dir)
        self._universe_cache: Dict[str, Set[str]] = {}
    
    def load_universe(self, universe_name: str, use_cache: bool = True) -> Set[str]:
        """
        加载 universe 符号集合
        
        Parameters
        ----------
        universe_name : str
            Universe 文件名
        use_cache : bool, optional
            是否使用缓存，默认 True
            
        Returns
        -------
        Set[str]
            符号集合
        """
        if use_cache and universe_name in self._universe_cache:
            return self._universe_cache[universe_name]
        
        universe_path = resolve_universe_path(universe_name, self.base_dir)
        if not universe_path:
            raise UniverseParseError(f"Universe file not found: {universe_name}")
        
        universe_data = load_universe_file(universe_path)
        symbols = extract_universe_symbols(universe_data)
        
        if use_cache:
            self._universe_cache[universe_name] = symbols
        
        return symbols
    
    def parse_strategy_universe(
        self,
        strategy_params: Union[Dict, Any],
        venue: str = "BINANCE",
        base_currency: str = "USDT",
        inst_type: str = "SWAP"
    ) -> Set[str]:
        """
        解析策略配置中的 universe 并返回 instrument IDs
        
        Parameters
        ----------
        strategy_params : Union[Dict, Any]
            策略参数
        venue : str, optional
            交易所名称
        base_currency : str, optional
            基准货币
        inst_type : str, optional
            标的类型
            
        Returns
        -------
        Set[str]
            Instrument ID 集合
        """
        universe_symbols = load_strategy_universe(strategy_params, self.base_dir)
        if not universe_symbols:
            return set()
        
        return parse_universe_symbols(universe_symbols, venue, base_currency, inst_type)
    
    def clear_cache(self) -> None:
        """清除缓存"""
        self._universe_cache.clear()