import importlib
from typing import Any, Type
from nautilus_trader.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

def load_strategy_class(module_path: str, class_name: str) -> Type[Strategy]:
    module = importlib.import_module(module_path)
    return getattr(module, class_name)

def load_strategy_config_class(module_path: str, class_name: str) -> Type[StrategyConfig]:
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
