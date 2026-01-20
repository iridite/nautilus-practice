# Agent Guidelines for nautilus-practice

This document provides coding guidelines for AI agents working in this repository. This is a quantitative trading project built on the NautilusTrader framework for backtesting and live trading cryptocurrency strategies.

## 📦 Project Overview

- **Framework**: NautilusTrader (nautilus-trader)
- **Python Version**: 3.12.12+ (strictly `>=3.12.12, <3.13`)
- **Package Manager**: `uv` (modern Python package manager)
- **Domain**: Cryptocurrency quantitative trading (perpetual futures)
- **Main Exchanges**: Binance, OKX

## 🛠️ Build/Test/Run Commands

### Environment Setup
```bash
# Install all dependencies
uv sync

# Activate virtual environment (if needed)
source .venv/bin/activate
```

### Running Tests
```bash
# Run all tests
uv run python -m unittest discover -s tests -p "test_*.py" -v

# Run a single test file
uv run python -m unittest tests/test_oi_divergence.py -v

# Run a specific test class
uv run python -m unittest tests.test_oi_divergence.TestCustomData -v

# Run a specific test method
uv run python -m unittest tests.test_oi_divergence.TestCustomData.test_open_interest_data_creation -v
```

### Running Backtests
```bash
# Main backtest entry point
uv run python main.py

# Strategy-specific backtest
uv run python backtest/backtest_oi_divergence.py

# Data preparation scripts
uv run python scripts/prepare_oi_divergence_data.py
```

### Python REPL
```bash
# Interactive shell with dependencies available
uv run python
uv run ipython  # if available
```

## 📝 Code Style Guidelines

### Import Organization
Follow PEP 8 import ordering:
1. Standard library imports
2. Third-party library imports (alphabetically)
3. Local/project imports (alphabetically)

```python
# Standard library
from collections import deque
from decimal import Decimal
from pathlib import Path
from typing import Optional

# Third-party
import pandas as pd
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId

# Local
from strategy.base import BaseStrategy, BaseStrategyConfig
from utils.custom_data import FundingRateData, OpenInterestData
```

### Type Hints
- **Required**: Use type hints for all function signatures and class attributes
- **Modern syntax**: Use Python 3.12+ union syntax (`int | None` instead of `Optional[int]`)
- **Precision**: Use `Decimal` for all financial calculations (prices, quantities, percentages)

```python
def calculate_position_size(
    equity: Decimal,
    price: Decimal,
    percentage: Decimal,
    leverage: int = 1,
) -> Decimal:
    """Calculate position size based on equity and risk parameters."""
    return (equity * percentage * leverage) / price

# Class attributes with type hints
class StrategyConfig:
    lookback_bars: int = 48
    stop_loss_pct: float | None = None
    funding_rate: Decimal = Decimal("0.0001")
```

### Naming Conventions
- **Classes**: PascalCase (e.g., `OIDivergence`, `FundingRateData`)
- **Functions/Methods**: snake_case (e.g., `calculate_position_size`, `on_bar`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `START_DATE`, `MAX_POSITIONS`)
- **Private methods**: Leading underscore (e.g., `_is_ready`, `_update_key_levels`)
- **Module names**: snake_case (e.g., `oi_divergence.py`, `custom_data.py`)

### Docstrings
Use detailed docstrings with parameter descriptions. Support mixed Chinese/English:

```python
"""
OI Divergence (持仓量背离) 策略

策略逻辑：
捕捉"杠杆驱动的假突破"，即价格突破关键位置但持仓量（Open Interest）
反向下降带来的均值回归机会。

Parameters
----------
instrument_id : InstrumentId
    合约标识符
open_interest : Decimal
    持仓量数值（通常为合约张数或 USD 计价）
ts_event : int
    事件发生时间戳（纳秒）
"""
```

### Error Handling
- Use explicit error handling with informative messages
- Log errors using NautilusTrader's logging system (`self.log.error()`)
- Validate inputs in strategy initialization

```python
def on_start(self):
    """Initialize strategy and validate configuration."""
    if not self.instrument:
        self.log.error(
            f"Could not find instrument {self.config.instrument_id}"
        )
        return
    
    self.log.info(f"Strategy initialized for {self.instrument.id}")
```

### Financial Calculations
- **Always use Decimal**: Never use `float` for prices, quantities, or percentages
- **Precision**: Be explicit about decimal places and rounding
- **Validation**: Check for division by zero and invalid ranges

```python
from decimal import Decimal

# Correct
funding_annual = funding_rate * Decimal("3") * Decimal("365") * Decimal("100")
position_size = Decimal("0.1")

# Wrong - do not use float for financial values
position_size = 0.1  # ❌
```

## 🏗️ Architecture Patterns

### Strategy Structure
Strategies should inherit from `BaseStrategy` and implement:
- `on_start()`: Initialize indicators and validate configuration
- `on_bar()`: Process bar data and execute trading logic
- `on_data()`: Handle custom data (OI, funding rates)
- Helper methods prefixed with `_` for internal logic

### Configuration Classes
Configuration should inherit from `BaseStrategyConfig`:
```python
class MyStrategyConfig(BaseStrategyConfig):
    # Strategy-specific parameters
    lookback_bars: int = 48
    entry_threshold: float = 0.05
    
    # Inherited from BaseStrategyConfig:
    # - trade_size, qty_percent, leverage
    # - stop_loss_pct, use_auto_sl
```

### Custom Data Types
Extend `nautilus_trader.core.data.Data` for market data:
```python
from nautilus_trader.core.data import Data

class OpenInterestData(Data):
    def __init__(self, instrument_id, open_interest, ts_event, ts_init):
        super().__init__()
        self._ts_event = ts_event
        self._ts_init = ts_init
        # ... implement required properties
```

## 🚫 Common Pitfalls

1. **Don't use float for financial calculations** - always use `Decimal`
2. **Don't forget to call `super().on_start()`** in strategy initialization
3. **Don't access positions without checking cache first**
4. **Don't hardcode file paths** - use `Path(__file__).parent` or `BASE_DIR`
5. **Don't commit secrets** - use `.env` files (already in `.gitignore`)

## 📁 Project Structure

```
nautilus-practice/
├── strategy/          # Trading strategy implementations
│   ├── base.py       # Base strategy class with common logic
│   └── *.py          # Specific strategies (oi_divergence, rs_squeeze, etc.)
├── utils/            # Utility modules
│   ├── custom_data.py         # Custom data types (OI, funding rates)
│   ├── oi_funding_adapter.py  # Data loaders and adapters
│   └── data_retrival.py       # OHLCV data fetching
├── backtest/         # Backtesting engines
├── tests/            # Unit tests (unittest framework)
├── scripts/          # Standalone scripts for data prep, etc.
├── config/           # Configuration files
├── data/             # Market data (gitignored, generated)
└── main.py           # Main entry point
```

## 🧪 Testing Guidelines

- Use `unittest` framework (standard library)
- Test file naming: `test_*.py`
- Test class naming: `Test<FeatureName>`
- Include docstrings explaining what each test validates
- Use `setUp()` for common test fixtures
- Test both happy paths and edge cases

## 📚 Key Dependencies

- **nautilus-trader**: Core backtesting and live trading framework
- **ccxt**: Exchange API integration for data fetching
- **pandas**: Data manipulation and analysis
- **scikit-learn**: Machine learning models
- **langchain**: LLM integration (for research/optimization)

## 🔧 Special Notes

- This project uses a custom Nautilus package index: `https://packages.nautechsystems.io/simple`
- Allow prereleases in `pyproject.toml` for alpha/dev Nautilus versions
- Chinese comments are acceptable and common in this codebase
- Data files are large and gitignored - run data preparation scripts first
