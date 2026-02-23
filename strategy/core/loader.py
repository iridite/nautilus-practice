import importlib
from typing import Any, Dict, Set, Type

from nautilus_trader.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy


def load_strategy_class(module_path: str, class_name: str) -> Type[Strategy]:
    """
    动态加载策略类。

    Args:
        module_path: 策略所在的模块路径 (e.g., 'strategies.rs_squeeze')
        class_name: 策略类名 (e.g., 'RSSqueezeStrategy')

    Returns:
        Type[Strategy]: 策略类
    """
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def load_strategy_config_class(module_path: str, class_name: str) -> Type[StrategyConfig]:
    """
    动态加载策略配置类。

    Args:
        module_path: 模块路径
        class_name: 配置类名

    Returns:
        Type[StrategyConfig]: 配置类
    """
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_config_fields(config_class: Type) -> Set[str]:
    """
    获取配置类及其父类中定义的所有字段名称。
    支持普通 dataclass, msgspec.Struct 以及继承体系。

    Args:
        config_class: 配置类

    Returns:
        Set[str]: 字段名称集合
    """
    fields = set()

    # 检查 __annotations__ (dataclasses / simple objects)
    if hasattr(config_class, "__mro__"):
        for base in config_class.__mro__:
            if hasattr(base, "__annotations__"):
                fields.update(base.__annotations__.keys())

    # 兼容 msgspec.Struct
    try:
        from msgspec import structs

        # 如果是 msgspec 结构体，可以尝试获取字段名
        if issubclass(config_class, structs.Struct):
            # 这里的具体实现取决于 msgspec 版本，通常 annotations 已经涵盖了
            pass
    except ImportError:
        pass

    return fields


def filter_strategy_params(params: Dict[str, Any], config_class: Type) -> Dict[str, Any]:
    """
    根据配置类的定义过滤参数字典，移除不属于该配置类的多余字段。

    Args:
        params: 原始参数字典
        config_class: 目标配置类

    Returns:
        Dict[str, Any]: 过滤后的参数字典
    """
    valid_fields = get_config_fields(config_class)
    return {k: v for k, v in params.items() if k in valid_fields}
