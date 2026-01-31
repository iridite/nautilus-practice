# Agent Guidelines for nautilus-practice

This document provides coding guidelines for AI agents working in this repository. This is a quantitative trading project built on the NautilusTrader framework for backtesting and live trading cryptocurrency strategies.

## 📦 Project Overview

- **Framework**: NautilusTrader 1.223.0
- **Python Version**: 3.12.12+ (strictly `>=3.12.12, <3.13`)
- **Package Manager**: `uv` (modern Python package manager)
- **Domain**: Cryptocurrency quantitative trading (perpetual futures)
- **Main Exchanges**: Binance, OKX
- **Code Scale**: 19,454 lines (optimized)
- **Test Coverage**: 106 tests, 100% pass rate

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
# Main backtest entry point (Funding Rate data auto-fetching)
uv run python main.py backtest

# Skip OI data checks (OHLCV only)
uv run python main.py backtest --skip-oi-data

# Note: OI data fetching is currently disabled (see OI Data Status section below)
# The following flags are inactive until local OI service is implemented:
# --force-oi-fetch, --oi-exchange

# Specify preferred exchange and retry settings for Funding Rate data
uv run python main.py backtest --oi-exchange binance --max-retries 5

# Strategy-specific backtest
uv run python backtest/backtest_oi_divergence.py

# Data preparation scripts
uv run python scripts/prepare_oi_divergence_data.py

# Test OI data integration
uv run python test_oi_integration.py

# View OI strategy example
uv run python examples/oi_strategy_example.py
```

### Backtest Engines
This project has two backtest engine implementations:

1. **Low-Level Engine** (`backtest/engine_low.py`): Direct BacktestEngine API
2. **High-Level Engine** (`backtest/engine_high.py`): BacktestNode with Parquet catalog

**Important Notes**:
- ⚠️ CSV data files must use either "datetime" or "timestamp" as time column name
- ⚠️ High-level engine expects "datetime" column by default
- ✅ Both engines are verified to work correctly with NautilusTrader 1.223.0

### Python REPL
```bash
# Interactive shell with dependencies available
uv run python
uv run ipython  # if available
```

### Data Preparation
```bash
# Generate trading pair Universe
uv run python scripts/generate_universe.py

# Prepare top market cap data
uv run python scripts/prepare_top_data.py

# Fetch instrument info
uv run python scripts/fetch_instrument.py
```

## 🏗️ Architecture Patterns

### Modular Architecture (2026-01-30 Refactored)

The project adopts a clear modular architecture with well-defined responsibilities:

**Main Entry** (`main.py` - 81 lines)
- Streamlined entry file responsible only for orchestration
- Command-line argument parsing
- Module coordination

**CLI Module** (`cli/`)
- `commands.py` - Command implementations (data checking, backtest execution)

**Data Management** (`utils/data_management/` - Unified Module)
- `validator.py` - Data validation and feed preparation
- `fetcher_manager.py` - Data fetching management
- `oi_funding_manager.py` - OI/Funding data management
- `data_retrival.py` - Main data retrieval logic
- `data_fetcher.py` - Multi-source OHLCV fetcher
- `data_limits.py` - Exchange data limits checking
- `data_loader.py` - CSV data loading utilities
- `data_manager.py` - High-level data manager
- `data_validator.py` - Data validation utilities

**Data Directory** (`data/`)
- Pure data storage (no code files)
- Subdirectories: `instrument/`, `raw/`, `parquet/`, `models/`, `record/`, `top/`

**Configuration System** (`core/` - Unified Architecture)
- `schemas.py` - Pydantic data models
- `loader.py` - YAML configuration loader
- `adapter.py` - Configuration adapter
- `settings.py` - Unified access interface
- Architecture: YAML → Pydantic Validation → Adapter → Application

**Strategy Module** (`strategy/`)
- `base.py` - Base strategy class
- `dependency_checker.py` - Strategy dependency checking
- `kalman_pairs.py` - Active strategy

### Dual Backtest Engine Architecture

1. **Low-Level Engine** (`backtest/engine_low.py`)
   - Direct use of BacktestEngine API
   - Full control over backtest process
   - Suitable for advanced users and custom requirements

2. **High-Level Engine** (`backtest/engine_high.py`)
   - Uses BacktestNode and Parquet catalog
   - Simplified configuration and usage
   - Suitable for rapid strategy validation

### Strategy Architecture

All strategies inherit from `BaseStrategy` and implement core lifecycle methods:

```python
class MyStrategy(BaseStrategy):
    def on_start(self):
        """Initialize indicators and validate configuration"""
        super().on_start()  # Must call

    def on_bar(self, bar):
        """Process Bar data and trading logic"""

    def on_data(self, data):
        """Process custom data (OI, funding rates)"""
```

**Configuration Classes** inherit from `BaseStrategyConfig`:
- Unified position management (`qty_percent`, `leverage`)
- Risk management parameters (`stop_loss_pct`, `use_auto_sl`)
- ATR risk mode (`use_atr_position_sizing`)
- Data dependency declaration (`data_types` list)

### Data Dependency Declaration Mechanism

Strategies declare required data types through a simple list:

```python
class MyStrategyConfig(BaseStrategyConfig):
    def __init__(self):
        super().__init__()
        # Simplified data dependency declaration
        self.data_types = ["oi", "funding"]  # Declare required data types
```

The system automatically before backtest:
1. Checks strategy's `data_types` list
2. Validates data file existence
3. Auto-downloads missing **Funding Rate** data (OI data fetching currently disabled)
4. Supports multi-exchange fallback and smart retry

**Note**: OI data auto-fetching is temporarily disabled. See "OI Data Status" section below.

### OI Data Status (2026-01-31)

**Current Status**: OI data fetching from third-party APIs is **temporarily disabled**.

**Reason**: 
- Binance OI API: Only provides 21 days of historical data
- OKX OI API: Only provides 90 days of historical data
- These limitations do not meet long-term backtesting requirements

**Future Plan**:
- Design and implement a local OI data collection service
- Continuously collect and store OI data for long-term historical analysis
- Service will run independently and maintain a comprehensive OI database

**Implementation Location**: `utils/data_management/data_retrival.py` - `ENABLE_OI_FETCH = False`

**For Developers**: 
- OI data fetching code structure is preserved but inactive
- Set `ENABLE_OI_FETCH = True` to re-enable after local service is ready
- Funding Rate data fetching remains fully functional

### Data Limits Auto-Check

System automatically checks exchange data limits (`utils/data_management/data_limits.py`):

```python
# Binance Funding Rate limit: ~90 days
# OKX Funding Rate limit: ~90 days
# Auto-validation and warnings during config building
```

### Utility Module Unified Interface

`utils/` module provides standardized utility functions to eliminate code duplication:

```python
from utils import (
    get_ms_timestamp,      # Time handling
    retry_fetch,           # Network retry
    check_data_exists,     # Data validation
    parse_timeframe,       # Symbol parsing
    load_ohlcv_csv,        # Data loading
    get_project_root,      # Path operations
    parse_universe_symbols # Config parsing
)
```

**Module Organization**:
- `time_helpers`: Timestamp conversion and handling
- `network`: HTTP requests and retry mechanism
- `validation`: Data file validation and checking
- `symbol_parser`: Trading pair symbol parsing and conversion
- `path_helpers`: Project path management (with caching)
- `config_helpers`: Universe configuration parsing
- `data_management/`: Unified data management module (see Data Management section above)

### Custom Data Types

Extends NautilusTrader's data system to support derivatives data:

- **OpenInterestData**: Open interest data (data fetching currently disabled, awaiting local service)
- **FundingRateData**: Funding rate data (fully functional)

Implemented through `utils.custom_data` and `utils.oi_funding_adapter` modules for data loading and adaptation.

**Note**: While OI data fetching is disabled, the data types and loading infrastructure remain intact for future use.

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
- **Module names**: snake
