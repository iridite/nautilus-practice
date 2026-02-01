# Nautilus Practice - Quantitative Trading Strategy Development Platform

A cryptocurrency quantitative trading strategy development and backtesting platform based on the NautilusTrader framework.

## 🚀 Project Overview

**Nautilus Practice** is a professional quantitative trading project focused on cryptocurrency perpetual contract strategy development, backtesting, and live trading. Built on the powerful NautilusTrader framework, it provides a complete strategy development toolchain.

### Core Features

- ✅ **Multi-Strategy Support**: OI Divergence, RS Squeeze, Dual Thrust and other strategy implementations
- ✅ **Dual Backtest Engines**: Low-level direct API and high-level Parquet directory support
- ✅ **Custom Data**: Integration of derivatives data such as Open Interest and Funding Rate
- ✅ **Fully Automated OI Data Acquisition**: Smart checking and automatic downloading of OI/Funding Rate data 🆕
- ✅ **Strategy Data Dependency Declaration**: Declarative data requirement management 🆕
- ✅ **Multi-Exchange**: Support for mainstream exchanges like Binance, OKX
- ✅ **Complete Testing**: 106 unit tests ensuring code quality
- ✅ **Modular Architecture**: Refactored utility modules eliminating code duplication

## 🛠️ Tech Stack

- **Framework**: NautilusTrader (nautilus-trader)
- **Python**: 3.12.12+ (strictly requires `>=3.12.12, <3.13`)
- **Package Manager**: `uv` (modern Python package manager)
- **Domain**: Cryptocurrency quantitative trading (perpetual contracts)
- **Exchanges**: Binance, OKX

## 📦 Installation and Environment Setup

### Prerequisites

- Python 3.12.12+
- uv package manager
- Git

### Quick Start

```bash
# 1. Clone repository
git clone <repository-url>
cd nautilus-practice

# 2. Install dependencies
uv sync

# 3. Activate virtual environment (optional)
source .venv/bin/activate

# 4. Run tests to verify installation
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 5. Quick start - Run backtest with OI data
uv run python main.py backtest
```

### 🚀 Quick Start Guide

```bash
# 1. Basic backtest (automatically fetches all required data)
uv run python main.py backtest

# 2. View OI strategy example
uv run python examples/oi_strategy_example.py

# 3. Test OI data integration functionality
uv run python test_oi_integration.py
```

**First Run**: The system will automatically detect strategy data requirements and download necessary OI and Funding Rate data from exchanges. This process may take a few minutes depending on data volume and network conditions.

### Environment Variable Configuration

```bash
# Copy environment variable template
cp .env.example .env

# Edit configuration file, add API keys, etc.
# Note: Never commit files containing real keys to version control
```

## 🔧 Usage Guide

### Running Backtests

```bash
# Main backtest entry (automatically checks and fetches all data)
uv run python main.py backtest

# Skip OI data check (use OHLCV data only)
uv run python main.py backtest --skip-oi-data

# Force re-download all OI data
uv run python main.py backtest --force-oi-fetch

# Specify preferred exchange and retry count
uv run python main.py backtest --oi-exchange binance --max-retries 5

# Specific strategy backtest
uv run python backtest/backtest_oi_divergence.py

# Data preparation script
uv run python scripts/prepare_oi_divergence_data.py
```

### 🆕 Automatic OI Data Acquisition

The system now supports fully automated Open Interest and Funding Rate data management:

#### New Command Line Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--skip-oi-data` | Skip OI data check and acquisition | False |
| `--force-oi-fetch` | Force re-download all OI data | False |
| `--oi-exchange` | Specify preferred exchange (binance/okx/auto) | auto |
| `--max-retries` | Set maximum retry count | 3 |

#### Smart Data Management Features

- **Auto Detection**: Automatically identifies required OI and Funding Rate data based on strategy configuration
- **Incremental Download**: Only downloads missing data files, avoiding duplicate downloads
- **Multi-Exchange Support**: Automatically switches to backup exchange when primary exchange fails
- **Smart Retry**: Automatic retry on network failure with progressive delay support
- **Data Validation**: Automatically validates data integrity and quality

### Data Preparation

```bash
# Generate trading pair Universe
uv run python scripts/generate_universe.py

# Prepare Top market cap data
uv run python scripts/prepare_top_data.py

# Fetch instrument information
uv run python scripts/fetch_instrument.py
```

### Running Tests

```bash
# Run all tests
uv run python -m unittest discover -s tests -p "test_*.py" -v

# Run single test file
uv run python -m unittest tests/test_oi_divergence.py -v

# Run specific test class
uv run python -m unittest tests.test_oi_divergence.TestCustomData -v
```

## 📁 Project Structure

```
nautilus-practice/
├── strategy/              # 📈 Trading strategy implementations
│   ├── base.py           #     Base strategy class
│   ├── oi_divergence_strategy.py  #     OI divergence strategy
│   ├── rs_squeeze.py     #     RS squeeze strategy
│   └── dual_thrust.py    #     Dual thrust strategy
├── utils/                # 🛠️ Utility modules (new architecture)
│   ├── __init__.py       #     Unified import interface
│   ├── time_helpers.py   #     Time processing utilities
│   ├── network.py        #     Network retry utilities
│   ├── validation.py     #     Data validation utilities
│   ├── symbol_parser.py  #     Symbol parsing utilities
│   ├── data_loader.py    #     Data loading utilities
│   ├── path_helpers.py   #     Path operation utilities
│   ├── config_helpers.py #     Configuration parsing utilities
│   ├── custom_data.py    #     Custom data types
│   └── oi_funding_adapter.py   #     OI/Funding data adapter
├── backtest/             # 🔬 Backtest engines
│   ├── engine_low.py     #     Low-level backtest engine
│   ├── engine_high.py    #     High-level backtest engine
│   └── exceptions.py     #     Exception definitions
├── tests/                # 🧪 Unit tests
├── scripts/              # 📜 Utility scripts
├── config/               # ⚙️ Configuration files
├── data/                 # 📊 Market data (gitignored)
├── docs/                 # 📚 Documentation
│   └── utils_guide.md    #     Utility module usage guide
└── main.py               # 🚪 Main entry point
```

## 🆕 Utility Module Architecture (Refactoring Highlights)

The project has undergone comprehensive refactoring, eliminating code duplication and establishing a modular utility architecture:

### Unified Import Interface

```python
# Recommended: Import through unified interface
from utils import (
    get_ms_timestamp,      # Time processing
    retry_fetch,           # Network retry
    check_data_exists,     # Data validation
    resolve_symbol_and_type,  # Symbol parsing
    load_csv_with_time_detection,  # Data loading
    get_project_root,      # Path operations
    load_universe_symbols_from_file  # Configuration parsing
)
```

### Modular Design

| Module | Functionality | Main Functions |
|--------|---------------|----------------|
| `time_helpers` | Time processing | `get_ms_timestamp()` |
| `network` | Network retry | `retry_fetch()` |
| `validation` | Data validation | `check_data_exists()` |
| `symbol_parser` | Symbol parsing | `resolve_symbol_and_type()`, `parse_timeframe()` |
| `data_loader` | Data loading | `load_csv_with_time_detection()` |
| `path_helpers` | Path operations | `get_project_root()` |
| `config_helpers` | Configuration parsing | `load_universe_symbols_from_file()` |

**Detailed Usage Guide**: 📖 [Utility Module Usage Guide](docs/utils_guide.md)

## 🏗️ Backtest Engines

### 1. Low-Level Engine (`backtest/engine_low.py`)
- Direct use of BacktestEngine API
- Full control over backtest process
- Suitable for advanced users and custom requirements

### 2. High-Level Engine (`backtest/engine_high.py`)  
- Uses BacktestNode and Parquet directories
- Simplified configuration and usage
- Suitable for quick strategy validation

### Important Notes
- ⚠️ CSV data files must use "datetime" or "timestamp" as time column name
- ⚠️ High-level engine expects "datetime" column by default
- ✅ Both engines verified working with NautilusTrader 1.223.0

## 📈 Strategy Development

### Base Strategy Structure

All strategies inherit from `BaseStrategy` and implement:

```python
from strategy.core.base import BaseStrategy, BaseStrategyConfig

class MyStrategyConfig(BaseStrategyConfig):
    # Strategy-specific parameters
    lookback_bars: int = 48
    entry_threshold: float = 0.05

class MyStrategy(BaseStrategy):
    def on_start(self):
        """Initialize indicators and validate configuration"""
        super().on_start()
        # Initialization logic
        
    def on_bar(self, bar):
        """Process Bar data and trading logic"""
        # Trading logic
        
    def on_data(self, data):
        """Process custom data (OI, funding rates)"""
        # Custom data processing
```

### 🆕 Strategy Data Dependency Declaration

The new data dependency declaration mechanism allows strategies to explicitly declare required data types:

```python
from strategy.core.base import BaseStrategy, BaseStrategyConfig

class MyStrategyConfig(BaseStrategyConfig):
    def __init__(self):
        super().__init__()
        
        # Declare required OI data dependency
        self.add_data_dependency(
            data_type="oi",
            required=True,
            period="1h",
            exchange="binance",
            auto_fetch=True
        )
        
        # Declare required Funding Rate data dependency
        self.add_data_dependency(
            data_type="funding",
            required=True,
            exchange="binance",
            auto_fetch=True
        )
        
        # Optional backup data source
        self.add_data_dependency(
            data_type="oi",
            required=False,
            period="4h",
            exchange="okx",
            auto_fetch=False
        )

class MyStrategy(BaseStrategy):
    def on_start(self):
        super().on_start()
        
        # Check data dependency status
        if self.base_config.has_oi_dependency():
            self.log.info("Strategy requires OI data")
        
        if self.base_config.has_funding_dependency():
            self.log.info("Strategy requires Funding Rate data")
```

### Existing Strategies

1. **OI Divergence Strategy**: Trend strategy based on open interest divergence
2. **RS Squeeze Strategy**: Breakout strategy based on relative strength squeeze
3. **Dual Thrust Strategy**: Classic dual thrust breakout strategy

**Example**: See [`examples/oi_strategy_example.py`](examples/oi_strategy_example.py) for complete data dependency declaration usage

## 📊 Data Management

### Supported Data Types

- **OHLCV**: Standard candlestick data
- **Open Interest**: Open interest data
- **Funding Rate**: Funding rate data
- **Custom Data**: Extended market data types

### Data Acquisition

```python
# Use refactored utility modules
from utils import batch_fetch_ohlcv, get_ms_timestamp

# Batch fetch OHLCV data
configs = batch_fetch_ohlcv(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31", 
    timeframe="1h",
    exchange_id="binance",
    base_dir=Path(".")
)
```

## 🧪 Testing Framework

The project includes 106 comprehensive unit tests:

```bash
# Run all tests
uv run python -m unittest discover -s tests -p "test_*.py" -v

# Test coverage
- Custom data type tests
- Strategy logic tests  
- Utility module tests
- Backtest engine tests
- Data loading tests
```

## ⚡ Performance Optimization

- **Caching Mechanism**: Built-in cache for `get_project_root()`
- **Batch Operations**: Support for batch data checking and processing
- **Smart Retry**: Intelligent delay strategy for network requests
- **Memory Optimization**: Efficient data loading and processing

## 🔒 Security Notes

- 🔑 API keys stored in `.env` file (in `.gitignore`)
- 🚫 Never commit files containing real keys
- 🔐 Use environment-specific configuration files (`live.env`, `test.env`)

## 🤝 Contribution Guidelines

### Code Style

The project follows strict coding standards:

- **Type Annotations**: All functions require complete type annotations
- **Modern Syntax**: Use Python 3.12+ union type syntax (`int | None`)
- **Financial Precision**: Financial calculations must use `Decimal` instead of `float`
- **Docstrings**: Detailed parameter descriptions, supporting mixed Chinese-English

### Adding New Features

1. Choose appropriate module or create new module
2. Follow naming conventions (`snake_case`)
3. Add complete type annotations and docstrings
4. Create corresponding unit tests
5. Update unified import interface

Detailed guide: [AGENTS.md](AGENTS.md)

## 📚 Documentation

- 📖 [Utility Module Usage Guide](docs/utils_guide.md)
- 📝 [Code Development Standards](AGENTS.md)
- 🆕 [OI Data Usage Guide](docs/oi_data_usage_guide.md)
- 📊 [OI Divergence Strategy Documentation](docs/oi_divergence_strategy.md)
- 📊 [Strategy Documentation](docs/)
- 🧪 [Testing Guide](tests/)
- 📋 [OI Data Integration Report](docs/AI%20Exec%20Reports/OI_DATA_INTEGRATION_REPORT.md)

## 📞 Support

When encountering issues:

1. Check usage examples in unit tests
2. Review docstrings in source code  
3. Run tests to verify functionality
4. Consult relevant documentation

## 🎯 TODO

- Research whether extremely negative net values during backtesting are feasible in reality

---

**Version**: v2.1 🆕
**Updated**: 2026-01-23
**New Features**: Fully automated OI data acquisition and strategy data dependency declaration
**Author**: Roo AI Assistant
**Framework**: NautilusTrader 1.223.0
