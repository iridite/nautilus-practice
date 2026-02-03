# Agent Guidelines for nautilus-practice

This document provides coding guidelines for AI agents working in this repository. This is a quantitative trading project built on the NautilusTrader framework for backtesting and live trading cryptocurrency strategies.

## 📦 Project Overview

- **Framework**: NautilusTrader 1.223.0
- **Python Version**: 3.12.12+ (strictly `>=3.12.12, <3.13`)
- **Package Manager**: `uv` (modern Python package manager)
- **Domain**: Cryptocurrency quantitative trading (perpetual futures)
- **Main Exchanges**: Binance, OKX
- **Code Scale**: ~12,817 lines, 59 Python files (optimized from 19,454 lines, -34.1%)
- **Test Coverage**: 84 tests, 100% pass rate
- **Documentation**: Organized in 4 categories (optimization/, analysis/, reviews/, refactoring/)

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
# Generate trading pair Universe (supports M/W-MON/2W-MON frequencies)
uv run python scripts/generate_universe.py

# Prepare top market cap data
uv run python scripts/prepare_top_data.py

# Fetch instrument info
uv run python scripts/fetch_instrument.py
```

**Universe Generator Configuration** (`scripts/generate_universe.py`):
- Supports multiple rebalance frequencies: Monthly (M), Weekly (W-MON), Bi-weekly (2W-MON)
- Automatic config validation on startup (MIN_COUNT_RATIO, TOP_Ns, REBALANCE_FREQ)
- Look-ahead bias prevention: T period data generates T+1 period universe
- Output format: `data/universe_{N}_{FREQ}.json`

## 🏗️ Architecture Patterns

### Modular Architecture (2026-01-30 Refactored)

The project adopts a clear modular architecture with well-defined responsibilities:

**Main Entry** (`main.py` - 81 lines)
- Streamlined entry file responsible only for orchestration
- Command-line argument parsing
- Module coordination

**CLI Module** (`cli/`)
- `commands.py` - Command implementations (data checking, backtest execution)
- `file_cleanup.py` - Automatic cleanup of old log/output files (moved from utils/)

**Data Management** (`utils/data_management/` - Unified Module, 7 files)
- `data_validator.py` - Data validation and feed preparation (merged from `validator.py`)
- `data_manager.py` - High-level data manager
- `data_retrieval.py` - Main data retrieval logic
- `data_fetcher.py` - Multi-source OHLCV fetcher
- `data_limits.py` - Exchange data limits checking
- `data_loader.py` - CSV data loading utilities

**Data Directory** (`data/`)
- Pure data storage (no code files)
- Subdirectories: `instrument/`, `raw/`, `parquet/`, `models/`, `record/`, `top/`

**Configuration System** (`core/` - Pydantic-based Architecture, 2026-01-31 Refactored)
- `schemas.py` - Pydantic data models (unified configuration classes)
- `loader.py` - YAML configuration loader
- `adapter.py` - Configuration adapter and unified access interface (310 lines, simplified)
- `exceptions.py` - Configuration exception classes
- Architecture: YAML → Pydantic Validation → Adapter → Application (3-layer design)
- **Removed**: `models.py` (dataclass models), `settings.py` (middleware layer)
- **Access Pattern**: `from core.adapter import get_adapter`
- **Refactoring Results**: 2 files deleted, 429 lines removed, architecture simplified from 4 layers to 3 layers

**Strategy Module** (`strategy/`)
- `core/base.py` - Base strategy class with unified position management
- `core/dependency_checker.py` - Strategy dependency checking
- `core/loader.py` - Strategy configuration loader
- `dk_alpha_trend.py` - DK Alpha Trend strategy (Squeeze + RS filtering)
- `dual_thrust.py` - Dual Thrust breakout strategy
- `kalman_pairs.py` - Kalman filter pairs trading strategy
</text>

<old_text line=175>
    def on_bar(self, bar):
        """Process Bar data and trading logic"""

    def on_data(self, data):
        """Process custom data (OI, funding rates)"""
```

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
- Timeframe dependency declaration (`timeframes` list)

### NautilusTrader Framework Constraints (2026-01-31)

**Critical: `Actor.config` is Read-Only**

NautilusTrader's `Strategy` class inherits from `Actor` (Rust implementation via pyo3 bindings). The `config` attribute is **read-only** and cannot be reassigned in `__init__`.

**❌ Incorrect Pattern** (causes `AttributeError`):
```python
class MyStrategy(BaseStrategy):
    def __init__(self, config: MyStrategyConfig):
        super().__init__(config)
        self.config = config  # ❌ ERROR: attribute is not writable
```

**✅ Correct Pattern**:
```python
class MyStrategy(BaseStrategy):
    def __init__(self, config: MyStrategyConfig):
        super().__init__(config)
        # ✅ self.config is already set by parent class
        # Access config directly: self.config.lookback_period
        self.lookback_period = config.lookback_period
```

**Why This Happens**:
- `Actor` class is implemented in Rust with pyo3 bindings
- `config` attribute has strict mutability control at the Rust level
- Framework design enforces configuration immutability after initialization
- `super().__init__(config)` already sets `self.config` correctly

**Best Practice**:
- Never reassign `self.config` in strategy `__init__`
- Access configuration via `self.config.parameter_name` or `config.parameter_name`
- Reference existing strategies (`dual_thrust.py`, `kalman_pairs.py`) for correct patterns

### Universe and RS Filtering Mechanism

**Two-Layer Filtering System** for optimal instrument selection:

**Layer 1: Universe Filtering** (Dynamic Pool)
- Filters active instruments based on trading volume and liquidity
- Updates periodically: Monthly (ME), Weekly (W-MON), or Bi-weekly (2W-MON)
- Prevents trading illiquid or delisted instruments
- Implementation: `_update_active_universe()` and `_is_symbol_active()`

**Layer 2: RS Filtering** (Relative Strength)
- Filters strong instruments within the active pool
- Compares instrument performance vs BTC benchmark
- Formula: `combined_rs = 0.4 * RS(5d) + 0.6 * RS(20d)`
- Entry condition: `combined_rs > 0` (outperforming BTC)
- Implementation: `_calculate_rs_score()` and `_check_relative_strength()`

**Execution Flow**:
```nautilus-practice/strategy/keltner_rs_breakout.py#L259-385
def on_bar(self, bar: Bar) -> None:
    # ... data updates ...
    
    # 4. Universe active status check: skip inactive instruments
    if not self._is_symbol_active():
        return
    
    # 7. RS check: only trade instruments outperforming BTC
    if not self._check_relative_strength():
        return
```

**Key Benefits**:
- Universe ensures liquidity and data quality
- RS ensures alpha generation (buying strength, not weakness)
- Two independent layers provide robust instrument selection
- Prevents trading inactive or weak instruments

### Data Dependency Declaration Mechanism

Strategies declare required data types and timeframes through simple lists:

```python
class MyStrategyConfig(BaseStrategyConfig):
    data_types: List[str] = ["oi", "funding"]  # Declare required data types
    timeframes: List[str] = ["main", "trend"]  # Declare required timeframes
```

**Data Types Declaration** (`data_types`):
- System automatically checks strategy's `data_types` list before backtest
- Validates data file existence
- Auto-downloads missing **Funding Rate** data (OI data fetching currently disabled)
- Supports multi-exchange fallback and smart retry

**Timeframe Declaration** (`timeframes`):
- Strategies declare which timeframes they need (e.g., `["main"]` or `["main", "trend"]`)
- System only loads declared timeframes, avoiding unnecessary data loading
- Default: `["main"]` if not specified
- Applies to all data loading modes: single instrument, universe, and benchmark

**Example Strategy Configurations**:
```yaml
# Single timeframe strategy (dual_thrust.yaml)
parameters:
  timeframes: ["main"]

# Multi-timeframe strategy (oi_divergence.yaml)
parameters:
  timeframes: ["main", "trend"]
```

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

**Implementation Location**: `utils/data_management/data_retrieval.py` - `ENABLE_OI_FETCH = False`

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

**Module Organization** (2026-02-01 Optimized):
- `time_helpers` (223 lines, 3 uses): Timestamp conversion and handling
- `network` (94 lines, 2 uses): HTTP requests and retry mechanism (optimized from 377 lines)
- `data_file_checker` (114 lines, 5 uses): Data file validation and checking
- `symbol_parser` (475 lines, 2 uses): Trading pair symbol parsing (reserved for multi-exchange support)
- `path_helpers` (50 lines, 1 use): Project path management with caching
- `universe` (229 lines, 1 use): Universe configuration parsing
- `instrument_loader` (61 lines, 3 uses): Instrument loading utilities
- `oi_funding_adapter` (478 lines, 3 uses): OI/Funding data adapter
- `custom_data` (160 lines, 2 uses): Custom data type definitions
- `data_management/` (7 files): Unified data management module

**Recent Optimizations** (2026-02-01):
- **Phase 1**: Removed 529 lines of dead code (10.9% reduction)
  - Simplified `__init__.py` from 240 to 97 lines
  - Moved `file_cleanup.py` to `cli/` module (single-use relocation)
  - Optimized `network.py` from 377 to 94 lines (removed unused utilities)
- **Phase 2**: Code quality improvements
  - Fixed duplicate exception class definitions (P0 priority)
  - Removed unused imports and fixed static analysis warnings
  - Organized documentation into thematic directories
- **Phase 3**: Tests directory optimization
  - Relocated independent test scripts to `scripts/` (2 files)
  - Removed duplicate `test_config_system.py`
  - Deleted disabled test file
  - Result: 13 → 10 files (-23.1%), 1,905 → 1,480 lines (-22.3%)
- **Total Impact**: 19,454 → 12,604 lines (-35.2% overall reduction)

### Custom Data Types

Extends NautilusTrader's data system to support derivatives data:

- **OpenInterestData**: Open interest data (data fetching currently disabled, awaiting local service)
- **FundingRateData**: Funding rate data (fully functional)

Implemented through `utils.custom_data` and `utils.oi_funding_adapter` modules for data loading and adaptation.

**Note**: While OI data fetching is disabled, the data types and loading infrastructure remain intact for future use.

## 🔧 Module Refactoring Best Practices (2026-02-01)

### Refactoring Strategy

### Code Optimization Analysis Workflow

**Step 1: Usage Analysis**
```python
# Analyze module import frequency
for root, dirs, files in os.walk("."):
    if ".venv" not in root:
        for file in files:
            if file.endswith(".py"):
                content = Path(root, file).read_text()
                # Count imports for each module
```

**Step 2: Identify Optimization Targets**
- 🔴 Low-use large files (>100 lines, ≤2 uses) - High priority
- 🟡 Single-use modules - Consider relocation
- 🟢 High-use modules (≥5 uses) - Keep as-is

**Step 3: Verify Before Deletion**
- Check if code is reserved for future features (e.g., multi-exchange support)
- Confirm zero actual usage with `grep` searches
- Verify functions aren't used internally within the module

### Refactoring Priority Levels

When refactoring large modules, follow a prioritized approach:

**P0 (Critical Issues)** - Fix immediately:
- Spelling errors in file names (affects all imports)
- Merge redundant modules with overlapping functionality
- Remove unused code with zero references

**P1 (Performance & Maintainability)** - Optimize next:
- Simplify over-engineered modules
- Create unified exception classes
- Refactor long functions (>100 lines) into smaller units
- Extract repeated code patterns

**P2 (Long-term Optimization)** - Plan for future:
- Analyze and resolve circular dependencies
- Extract common utilities to shared modules
- Document dependency graphs

### Module Consolidation Guidelines

When merging redundant modules:
1. **Analyze usage**: Use `grep` to find all import references
2. **Preserve functionality**: Move all functions to the target module
3. **Update imports**: Update `__init__.py` and all dependent files
4. **Verify tests**: Ensure 100% test pass rate after changes
5. **Document changes**: Update architecture documentation

**Example 1**: Merged `validator.py` and `fetcher_manager.py` into `data_validator.py` and `data_manager.py`, reducing module count by 13.6%.

**Example 2** (2026-02-01): Utils module optimization
- Simplified `__init__.py`: 240 → 97 lines (-59.6%)
- Relocated `file_cleanup.py` to `cli/` (single-use module)
- Optimized `network.py`: 377 → 94 lines (-75.1%)
- Total reduction: 529 lines (10.9%)

### Code Extraction Patterns

**Extract repeated timestamp conversions**:
```python
# Before: Repeated in multiple files
ts = pd.Timestamp(date_str)
if ts.tz is not None:
    ts = ts.tz_localize(None)

# After: Unified in time_helpers.py
from utils.time_helpers import parse_date_to_timestamp
ts = parse_date_to_timestamp(date_str)
```

**Extract data validation logic**:
```python
# Before: Scattered validation code
if not csv_path.exists():
    raise DataLoadError(f"File not found: {csv_path}")

# After: Unified exception classes
from utils.exceptions import DataValidationError
if not csv_path.exists():
    raise DataValidationError(f"File not found: {csv_path}")
```

### Dependency Analysis

Use simple scripts to analyze module dependencies:
```python
# Check for circular dependencies
for f in Path('utils/data_management').glob('*.py'):
    imports = [line for line in f.read_text().split('\n') 
               if line.startswith('from .')]
    print(f'{f.stem} → {imports}')
```

**Healthy dependency pattern** (no cycles):
```
data_manager → data_retrieval → data_fetcher
data_validator → data_manager
oi_funding_manager → data_manager
```

### Refactoring Metrics

Track these metrics during refactoring:
- **Module count**: Target 10-20% reduction
- **Code lines**: Net reduction through deduplication
- **Test coverage**: Maintain 100% pass rate
- **Import complexity**: Reduce cross-module dependencies

**Example results** (Project-wide optimization):
- Code: 19,454 → 13,158 lines (-32.4% reduction)
- Utils module: 4,868 → 4,339 lines (-10.9%)
- Tests: 84/84 (100% pass)
- Dependencies: Clear hierarchy, no cycles

**Utils Module Optimization Case Study** (2026-02-01):
1. **Analysis Phase**: Used automated scripts to analyze import frequency and file sizes
2. **Identified Issues**:
   - `__init__.py`: 240 lines with unused helper functions
   - `network.py`: 377 lines but only `retry_fetch()` used
   - `file_cleanup.py`: 103 lines, single use in `cli/commands.py`
3. **Actions Taken**:
   - Removed unused functions: `batch_validate_data()`, `get_utils_info()`, `_check_python_version()`
   - Deleted 7 unused functions from `network.py` (RateLimiter, decorators, helpers)
   - Relocated single-use module to its usage location
4. **Results**: 529 lines removed, 100% test pass rate maintained
5. **Key Lesson**: Always verify if "unused" code is reserved for future features before deletion

### Single-Use Module Relocation Pattern

When a module is only used in one location:

**Decision Criteria**:
- ✅ Relocate if: Module is tightly coupled to single usage location
- ✅ Relocate if: Module size is small-to-medium (<200 lines)
- ❌ Keep if: Module provides independent, reusable functionality
- ❌ Keep if: Module is reserved for future multi-location usage

**Example**: `file_cleanup.py` (103 lines, 1 use)
```python
# Before: utils/file_cleanup.py
# After: cli/file_cleanup.py
# Update import: from utils.file_cleanup → from .file_cleanup
```

### Reserved Code vs Dead Code

**Reserved Code** (Keep):
- Explicitly documented for future features (e.g., "multi-exchange support")
- Part of a complete API surface (even if partially unused)
- Infrastructure for planned functionality

**Dead Code** (Remove):
- Zero references in codebase
- No documentation indicating future use
- Redundant or superseded functionality

**Example**: `symbol_parser.py` contains 7 unused functions but is **reserved** for multi-exchange support - keep intact.

## 🔍 Code Scanning & Issue Identification (2026-02-01)

### Systematic Scanning Methodology

**Scan Order** (by criticality):
1. `core/` - Configuration system (runtime errors impact all modules)
2. `strategy/` - Strategy implementations (trading logic correctness)
3. `backtest/` - Backtest engines (result accuracy)
4. `utils/` - Utility modules (widespread usage)
5. `sandbox/` - Live trading framework (production risk)

**Analysis Tools**:
```bash
# Code statistics
find module/ -name "*.py" | xargs wc -l | sort -rn

# Import frequency analysis
grep -r "from module import" --include="*.py" | wc -l

# Dependency checking
grep -r "^from\|^import" module/*.py
```

### Issue Classification

**🔴 P0 - Runtime Issues** (Fix immediately):
- Missing API credentials or configuration
- Null pointer / AttributeError risks
- Type mismatches causing crashes
- Resource leaks (file handles, connections)
- Exception handling gaps

**🟡 P1 - Design Issues** (Optimize next):
- Circular dependencies
- Inconsistent exception handling
- Unclear module responsibilities
- High coupling between modules
- Large files (>1000 lines) with multiple responsibilities

**🟢 P2 - Long-term Optimization** (Plan for future):
- Reserved code for future features
- Architecture improvements
- Performance optimizations
- Documentation enhancements

### Priority Decision Matrix

| Impact | Frequency | Priority | Action |
|--------|-----------|----------|--------|
| High | High | P0 | Fix immediately |
| High | Low | P1 | Fix in sprint |
| Low | High | P1 | Optimize when beneficial |
| Low | Low | P2 | Document for future |

### Recent Fixes Summary (2026-02-01)

**P0 Issues Resolved**:
- ✅ `sandbox/engine.py`: API credentials not passed to config objects (commit `7482aec`)
- ✅ `sandbox/engine.py`: Environment parameter missing (SANDBOX vs LIVE)
- ✅ `strategy/core/base.py`: Added `max_positions` parameter support
- ✅ `sandbox/engine.py`: Fixed `btc_instrument_id` empty string parsing error
- ✅ `strategy/keltner_rs_breakout.py`: Funding Rate Guard 执行流程错误 (commit `db59583`)

**Strategy Compliance Audit (2026-02-01)**:
- ✅ **Keltner RS Breakout (KRB)**: 100% 符合 Golden Specification
  - 添加 Funding Rate Guard (资金费率 > 0.05% 拒绝开仓)
  - 修复执行顺序：持仓管理优先于 Funding Rate 检查，避免止损失效
  - 数学逻辑验证：EMA(20) + 2.25*ATR (静态倍数)，Wilder's ATR
  - RS 逻辑验证：Symbol% vs BTC% 百分比变化比较
  - 仓位计算验证：波动率倒数模型 (1.0% 普通 / 1.5% Squeeze)
  - 代码可读性：统一注释编号 (1-8)，改进异常处理日志

**P1 Issues Identified**:
- 📋 `core/ ↔ utils/`: Circular dependency (documented in P2)
- 📋 `utils/data_management/`: Inconsistent exception handling
- 📋 `strategy/core/base.py`: Config reassignment risk (documented in guidelines)

**Code Quality Metrics**:
- Code reduction: 19,454 → 12,661 lines (-35.2%)
- Test pass rate: 84/84 (100%)
- P0 issues: 0 (all resolved)
- P1 issues: 3 (impact controlled)

### Scanning Best Practices

1. **Start with tests**: Run full test suite before and after changes
2. **Analyze usage**: Use `grep` to find actual usage patterns
3. **Check documentation**: Verify if "unused" code is reserved for future
4. **Verify dependencies**: Map import relationships before refactoring
5. **Maintain stability**: Never sacrifice test pass rate for optimization

## 📋 Optimization Documentation

Project optimization efforts are documented in `docs/optimization/`:

- **P0_critical_issues.md**: Critical issues requiring immediate fixes
  - Status: ✅ Completed - Duplicate exception classes removed
- **P1_performance_optimization.md**: Performance and maintainability improvements
  - Status: ✅ Evaluated - `data_loader.py` (730 lines) assessed, no split needed
- **P2_long_term_goals.md**: Long-term architectural improvements
  - Status: 📋 Documented - `core ↔ utils` circular dependency recorded

**Key Principles**:
- P0: Fix immediately (correctness, maintainability)
- P1: Optimize when beneficial (performance, code quality)
- P2: Plan for future (architecture, design patterns)
- Always maintain 100% test pass rate
- Prioritize stability over theoretical perfection

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
from strategy.core.base import BaseStrategy, BaseStrategyConfig
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

---

## 🔧 Code Quality Tools (2026-02-01)

### Tool Integration

项目已集成以下代码质量工具：

**Ruff** - 代码检查和格式化
```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
ignore = ["E501"]
```

**Mypy** - 静态类型检查
```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
```

**Pre-commit Hooks**
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

### Usage

```bash
# 运行代码检查
uv run ruff check .

# 自动修复问题
uv run ruff check . --fix

# 格式化代码
uv run ruff format .

# 类型检查
uv run mypy strategy/ utils/ backtest/

# 安装 pre-commit hooks
uv run pre-commit install
```

### Acceptable Code Style Issues

以下代码风格问题是可接受的，无需修复：

1. **E402 (module-import-not-at-top-of-file)**: 入口文件需要先修改 `sys.path` 再导入
   - `main.py`, `backtest/engine_low.py`, `sandbox/engine.py`
   
2. **F401 (unused-import) in tests**: 测试文件中用于测试导入功能的导入
   - `tests/test_engine_low_rewrite.py`

---

## 📊 Optimization Lessons Learned (2026-02-01)

### Memory Management Patterns

**Case Study: OrderedDict vs deque**

**错误的优化建议**: 将 `OrderedDict` 替换为 `deque` 以减少内存占用

**问题分析**:
```python
# strategy/keltner_rs_breakout.py:99-100
self.price_history = OrderedDict()  # {timestamp: price}
self.btc_price_history = OrderedDict()

# 关键使用场景 (line 353-354)
symbol_prices = [self.price_history[ts] for ts in recent_ts]
btc_prices = [self.btc_price_history[ts] for ts in recent_ts]
```

**为什么不能优化**:
1. 需要按时间戳索引 - `dict[timestamp]`
2. 需要计算时间戳交集 - `set(dict.keys())`
3. deque 只支持位置索引 - `deque[0]`

**结论**: 在评估优化方案前，必须先分析数据结构的实际使用场景。

### File Size Guidelines

**不建议拆分的情况**:
- 功能高度内聚（如数据加载、引擎核心）
- 函数间依赖紧密
- 核心模块被广泛使用
- 拆分会增加模块间耦合

**已评估的文件**:
- `backtest/engine_high.py` (1,226 行) - 已添加代码分区注释，不拆分
- `utils/data_management/data_loader.py` (751 行) - 功能内聚，不拆分
- `core/schemas.py` (576 行) - 配置类集中管理，不拆分

**原则**: "稳定性 > 理论完美"

---

## 📁 Project Maintenance (2026-02-01)

### Documentation Structure

优化文档组织在 `docs/optimization/` 目录：
- `P0_critical_issues.md` - 关键问题（已完成）
- `P1_performance_optimization.md` - 性能优化（部分完成）
- `P2_long_term_goals.md` - 长期目标（已记录）

避免创建冗余的综合报告文件，保持文档结构简洁。

### Repository Sync

项目支持自动同步到公开仓库：
- 配置文件: `.sync-config`
- 同步脚本: `scripts/sync_to_public.sh`
- 自动移除敏感内容（策略代码、配置文件）

---

## ✅ Completed Optimizations (2026-02-01)

### Code Quality
- ✅ 统一日志系统（print → logger）
- ✅ 代码风格修复（143 → 58 个问题）
- ✅ 添加代码质量工具（ruff, mypy, pre-commit）

### Performance
- ✅ 数据加载缓存（LRU 缓存机制）
- ✅ 指标计算优化（NumPy 向量化）

### Testing
- ✅ 测试覆盖率提升（95 → 103 个测试）
- ✅ 新增测试文件（8 个）

### Documentation
- ✅ README 翻译为英文
- ✅ 优化文档整理
- ✅ OrderedDict 优化评估记录

### Backtest Engine Fixes (2026-02-02)
- ✅ 修复高级回测引擎的 logger 参数错误（sys.stdout.write）
- ✅ 修复高级回测引擎的时间戳转换问题（毫秒时间戳 → 1970 年）
- ✅ 移除高级回测引擎的 OI/Funding 数据加载逻辑（避免重复警告）
- ✅ 移除回测输出中的无意义分割线
- ✅ 统一低级和高级回测的 JSON 输出位置（output/backtest/result）
- ✅ 统一低级和高级回测的 JSON 文件命名格式（移除 low_ 前缀）
- ✅ 高级回测引擎完全修复，回测结果：176.26 USDT（超过 170 USDT 目标）

### Code Structure Improvements (2026-02-03)
- ✅ 修复高级回测引擎模块分隔符位置问题（7处）
  - 问题：模块级分隔符注释被错误地放在函数内部，导致代码可读性下降
  - 影响函数：`_load_instruments`, `_check_parquet_coverage`, `_verify_data_consistency`, `_create_strategy_configs`, `_run_backtest_with_custom_data`, `_load_custom_data_to_engine`, `_print_results`
  - 修复：将所有模块分隔符移至函数之间，符合 Python 代码规范
  - 结果：提升代码可读性，消除 IDE 警告，不影响运行时行为

### Universe Generator Optimization (2026-02-02)
- ✅ 添加模块级文档注释（功能说明、核心特性、使用方法、注意事项）
- ✅ 修复双周频率 resample 语法错误（2W → 2W-MON）
- ✅ 修复周度/双周时间字符串重复问题（独立格式化逻辑）
- ✅ 优化稳定币列表（移除 UST/EURS/EUR/GBP/KNC，添加 FDUSD/PYUSD/USDD）
- ✅ 添加配置参数验证函数（validate_config）
  - MIN_COUNT_RATIO 范围验证：(0, 1]
  - TOP_Ns 格式验证：非空且包含正整数
  - REBALANCE_FREQ 有效性验证：M/W-MON/2W-MON
- ✅ 改进异常处理（细化异常类型：FileNotFoundError、EmptyDataError、KeyError、ValueError）
- ✅ 改进文件名解析（使用 file_path.stem 并验证格式）
- ✅ 添加类型注解（period_start: pd.Timestamp）
- ✅ 添加内存优化（显式删除 DataFrame 释放内存）
- ✅ 消除魔法数字（sample_size = min(10, len(...))）
- ✅ 添加边界情况注释（最后周期不生成 universe 的说明）

**Universe Generator 代码审计经验**:
- 未来函数检查：确认 T 期数据生成 T+1 期 universe，无前视偏差
- 高优先级问题：语法错误、逻辑错误、数据质量问题
- 中低优先级问题：参数验证、异常处理、代码质量
- 可选优化：内存效率、输入验证、数据完整度调整
- 审计流程：先修复严重问题，再处理中低优先级，最后可选优化

### Strategy Bug Fixes (2026-02-03)
- ✅ 修复 Keltner RS Breakout 策略数量精度问题
  - 问题：低级回测引擎报错，ATR 风险模式计算的数量小于标的最小增量时被四舍五入为零
  - 原因：某些标的（如 AVAXUSDT-PERP）要求整数数量（size_increment=1），但计算出的数量可能为 0.22
  - 修复：在调用 `make_qty` 前检查数量是否小于 `size_increment`，避免抛出异常
  - 位置：`strategy/keltner_rs_breakout.py:510-520`
  - 影响：仓位过小的交易信号会被跳过并记录警告，不影响策略核心逻辑
  - 测试：低级/高级回测引擎均已验证通过

### Strategy Feature Enhancements (2026-02-03)
- ✅ 添加 BTC 市场状态过滤器（Market Regime Filter）
  - 目标：防止在 BTC 弱势或横盘时做多山寨币（80% 假突破）
  - 实现：
    - BTC 趋势判定：`BTC > SMA(200)`
    - BTC 波动率检查：`ATR% < 3%`（防止崩盘期间开仓）
  - 配置参数：
    - `enable_btc_regime_filter: bool = True` - 过滤器开关
    - `btc_regime_sma_period: int = 200` - BTC 趋势判定周期
    - `btc_regime_atr_period: int = 14` - BTC 波动率计算周期
    - `btc_max_atr_pct: float = 0.03` - BTC ATR 百分比阈值（3%）
  - 集成位置：Universe 检查之后、Funding Rate 之前
  - 核心设计：
    - 使用 ATR 百分比（ATR/Price）而非绝对值，避免价格变化导致误判
    - 保守策略：BTC 指标未就绪时返回 False，不开仓
    - 过滤器顺序：先检查市场环境（BTC），再检查个股条件
  - 位置：`strategy/keltner_rs_breakout.py:62-69, 114-118, 268-285, 393-406, 431-451, 326-329`

- ✅ Universe 和 RS 筛选机制设计（2026-02-03）
  - **两层独立筛选机制**：
    1. **Universe 筛选（第一层）**：
       - 基于历史成交额动态生成活跃币种池
       - 支持月度（ME）、周度（W-MON）、双周（2W-MON）更新
       - 避免未来函数：T 期数据生成 T+1 期交易池
       - 数据质量控制：剔除稳定币，过滤数据不完整的新币
       - 实现位置：`strategy/keltner_rs_breakout.py:167-219`
    2. **RS 筛选（第二层）**：
       - 在活跃币种池内进一步筛选强势币种
       - RS 计算：加权组合 `0.4 * RS(5d) + 0.6 * RS(20d)`
       - 筛选条件：`combined_rs > 0`（相对 BTC 表现更强）
       - 实现位置：`strategy/keltner_rs_breakout.py:485-544`
  - **执行流程**（`on_bar` 方法）：
    ```python
    # 4. Universe 活跃状态检查：非活跃币种不开仓
    if not self._is_symbol_active():
        return
    
    # 7. RS 检查：活跃池内筛选强势币种
    if not self._check_relative_strength():
        return
    ```
  - **设计目标**：
    - Universe 控制交易池规模和流动性
    - RS 确保买入的是活跃池中的强势标的
    - 两层筛选独立运行，互不干扰
  - **配置示例**：
    ```yaml
    parameters:
      universe_top_n: 25        # Universe 池大小
      universe_freq: W-MON      # 周度更新
      rs_short_lookback_days: 5 # RS 短期回溯
      rs_long_lookback_days: 20 # RS 长期回溯
    ```

**策略开发经验教训**:
1. **数量精度问题**：
   - 不同标的的 `size_increment` 和 `size_precision` 不同
   - 必须在调用 `make_qty` 前检查数量是否满足最小要求
   - 对于整数数量标的，ATR 风险模式可能导致数量过小
2. **市场状态过滤器设计**：
   - ATR 应使用百分比（ATR/Price）而非绝对值
   - 过滤器顺序很重要：先市场环境，再个股条件
   - 必须添加配置开关便于 A/B 测试
   - Warmup 检查必须完整，避免使用未就绪的指标
3. **Universe 和 RS 筛选机制**：
   - Universe 先筛选活跃币种池（基于成交额和数据完整性）
   - RS 在活跃池内进一步筛选强势币种（相对 BTC 表现）
   - 两层独立筛选确保买入的是活跃池中的强势标的
   - 避免买入流动性差或弱势的币种
4. **代码审查流程**：
   - 实施前必须进行逻辑设计检查
   - 确保符合行业规范（ATR 计算方法、过滤器顺序等）
   - 检查边界条件和异常情况
   - 验证配置参数的合理性

### P0 Code Quality Fixes (2026-02-03)
- ✅ 异常处理优化（13处修复）
  - 替换 `except Exception: pass` 为具体异常类型
  - 添加详细错误日志
  - 位置：`backtest/engine_high.py` (10处)、`backtest/engine_low.py` (1处)、`utils/data_management/` (2处)
- ✅ 文件资源管理（1处修复）
  - 使用 `with` 语句避免文件句柄泄漏
  - 位置：`backtest/engine_high.py:481`
- ✅ 网络请求超时保护（4处修复）
  - 添加 `MAX_ITERATIONS = 1000` 常量
  - 防止 API 故障时无限等待
  - 位置：`utils/data_management/data_retrieval.py`
- ✅ 提交记录：`5f6aaa2`
- ✅ 测试通过率：103/103 (100%)
- 参考：`docs/optimization/critical_code_review_2026-02-03.md`

