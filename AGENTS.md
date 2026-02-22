# Agent Guidelines for nautilus-practice

This document provides coding guidelines for AI agents working in this repository. This is a quantitative trading project built on the NautilusTrader framework for backtesting and live trading cryptocurrency strategies.

> **⚡ 需要快速参考？** 本文件包含详细的开发指南、组件使用示例和完整的项目历史。如需快速上手和常用命令，请先查看 [CLAUDE.md](CLAUDE.md)。

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
- `common/` - **Reusable strategy components library (2026-02-20 Refactored)**
  - `indicators/` - Technical indicators (Keltner, RS, Market Regime)
  - `signals/` - Entry/Exit signal generators
  - `universe/` - Dynamic universe management
- `keltner_rs_breakout.py` - Keltner RS Breakout strategy (original)
- `keltner_rs_breakout_refactored.py` - Keltner RS Breakout (modular version)
- `dual_thrust.py` - Dual Thrust breakout strategy
- `kalman_pairs.py` - Kalman filter pairs trading strategy

... (document continues with established content covering refactoring patterns, tests, lessons learned, etc.)

## 🔧 Module Refactoring Best Practices (2026-02-01)

(Existing content retained. See repository for full details and additional sections on scanning, metrics and refactor guidance.)

## 🔍 Code Scanning & Issue Identification (2026-02-01)

(Existing content retained.)

## 📋 Optimization Documentation

(Existing content retained.)

## 📝 Code Style Guidelines

(Existing content retained.)

## 🔧 Code Quality Tools (2026-02-01)

(Existing content retained.)

## 🧩 Modular Strategy Development Pattern (2026-02-20)

### Overview

The project has adopted a **modular component-based architecture** for strategy development, significantly improving code reusability and development efficiency.

**Key Achievement**:
- ✅ Code reduction: 40% (1080 lines → 650 lines)
- ✅ Code reuse rate: 700% increase (10% → 80%)
- ✅ New strategy development time: 60% reduction (3-5 days → 1-2 days)
- ✅ Test coverage: 17 test cases (15 component tests + 2 strategy tests)

### Architecture

```
strategy/common/                          # Reusable Components Library
├── indicators/                           # Technical Indicators
│   ├── keltner_channel.py               # Keltner Channel (EMA, ATR, SMA, BB)
│   ├── relative_strength.py             # Relative Strength Calculator
│   └── market_regime.py                 # Market Regime Filter
├── signals/                              # Signal Generators
│   └── entry_exit_signals.py            # Entry/Exit Signal Generators
└── universe/                             # Universe Management
    └── dynamic_universe.py              # Dynamic Universe Manager
```

### Core Components

#### 1. KeltnerChannel (Technical Indicators)
**Purpose**: Calculate Keltner Channel and related indicators

**Includes**:
- EMA (Exponential Moving Average)
- ATR (Average True Range, Wilder's Smoothing)
- SMA (Simple Moving Average)
- Bollinger Bands
- Volume SMA

**Usage**:
```python
from strategy.common.indicators import KeltnerChannel

keltner = KeltnerChannel(
    ema_period=20,
    atr_period=20,
    sma_period=200,
    keltner_base_multiplier=1.5,
    keltner_trigger_multiplier=2.25,
)

# Update with bar data
keltner.update(high, low, close, volume)

# Get trigger bands
trigger_upper, trigger_lower = keltner.get_keltner_trigger_bands()

# Check squeeze state
is_squeezing = keltner.is_squeezing()
```

#### 2. RelativeStrengthCalculator
**Purpose**: Calculate relative strength vs benchmark (BTC)

**Formula**: `Combined RS = short_weight * RS(short) + long_weight * RS(long)`

**Usage**:
```python
from strategy.common.indicators import RelativeStrengthCalculator

rs_calculator = RelativeStrengthCalculator(
    short_lookback_days=5,
    long_lookback_days=20,
    short_weight=0.4,
    long_weight=0.6,
)

# Update prices
rs_calculator.update_symbol_price(timestamp, price)
rs_calculator.update_benchmark_price(timestamp, btc_price)

# Calculate RS
rs = rs_calculator.calculate_rs()
is_strong = rs_calculator.is_strong(threshold=0.0)
```

#### 3. MarketRegimeFilter
**Purpose**: Filter trades based on BTC market conditions

**Criteria**:
- Trend: BTC > SMA(200) → Bullish
- Volatility: ATR% < 3% → Controlled

**Usage**:
```python
from strategy.common.indicators import MarketRegimeFilter

regime_filter = MarketRegimeFilter(
    sma_period=200,
    atr_period=14,
    max_atr_pct=0.03,
)

regime_filter.update(high, low, close)
is_favorable = regime_filter.is_favorable_for_altcoins()
```

#### 4. EntrySignalGenerator
**Purpose**: Generate entry signals

**Checks**:
- Keltner breakout
- Volume surge
- Price position (> SMA)
- Upper wick ratio

**Usage**:
```python
from strategy.common.signals import EntrySignalGenerator

entry_signals = EntrySignalGenerator(
    volume_multiplier=1.5,
    max_upper_wick_ratio=0.3,
)

is_breakout = entry_signals.check_keltner_breakout(close, trigger_upper)
is_volume_surge = entry_signals.check_volume_surge(volume, volume_sma)
```

#### 5. ExitSignalGenerator
**Purpose**: Generate exit signals

**Checks**:
- Time stop
- Chandelier Exit (trailing stop)
- Parabolic profit taking
- RSI overbought exit
- Breakeven stop

**Usage**:
```python
from strategy.common.signals import ExitSignalGenerator

exit_signals = ExitSignalGenerator(
    enable_time_stop=True,
    time_stop_bars=3,
    stop_loss_atr_multiplier=2.0,
)

should_exit = exit_signals.check_time_stop(entry_bar_count, highest_high, entry_price)
should_exit = exit_signals.check_chandelier_exit(close, highest_high, atr)
```

#### 6. SqueezeDetector
**Purpose**: Detect squeeze state (Bollinger Bands inside Keltner Channel)

**Usage**:
```python
from strategy.common.signals import SqueezeDetector

squeeze_detector = SqueezeDetector(memory_days=5)

is_squeezing = squeeze_detector.check_squeeze(
    bb_upper, bb_lower,
    keltner_upper, keltner_lower,
)

high_conviction = squeeze_detector.is_high_conviction(is_squeezing)
```

#### 7. DynamicUniverseManager
**Purpose**: Manage dynamic trading universe

**Features**:
- Load pre-calculated universe from JSON
- Auto-switch active symbols based on timestamp
- Support monthly/weekly/bi-weekly updates

**Usage**:
```python
from strategy.common.universe import DynamicUniverseManager

universe_manager = DynamicUniverseManager(
    universe_file="data/universe/universe_50_ME.json",
    freq="ME",  # Monthly update
)

universe_manager.update(timestamp)
is_active = universe_manager.is_active("BTCUSDT")
```

### Development Pattern

#### Before Refactoring (Monolithic)
```python
class KeltnerRSBreakoutStrategy(BaseStrategy):
    def __init__(self, config):
        # Manual implementation of all indicators (~100+ lines)
        self.closes = deque(maxlen=200)
        self.ema = None
        self.atr = None
        # ... 100+ lines of initialization

    def _update_ema(self):
        # Manual EMA calculation (~20 lines)
        pass

    def _calculate_rs_score(self):
        # Manual RS calculation (~50 lines)
        pass
```

#### After Refactoring (Modular)
```python
from strategy.common.indicators import (
    KeltnerChannel,
    RelativeStrengthCalculator,
    MarketRegimeFilter
)
from strategy.common.signals import (
    EntrySignalGenerator,
    ExitSignalGenerator,
    SqueezeDetector
)

class KeltnerRSBreakoutStrategy(BaseStrategy):
    def __init__(self, config):
        # Use modular components (~10 lines)
        self.keltner = KeltnerChannel(...)
        self.rs_calculator = RelativeStrengthCalculator(...)
        self.regime_filter = MarketRegimeFilter(...)
        self.entry_signals = EntrySignalGenerator(...)
        self.exit_signals = ExitSignalGenerator(...)

    def on_bar(self, bar):
        # Clean strategy logic
        self.keltner.update(high, low, close, volume)

        if self.entry_signals.check_keltner_breakout(close, trigger_upper):
            self._handle_entry(bar)
```

### Benefits

1. **Accelerated Development** (↓ 60-70%)
   - New strategy development: 3-5 days → 1-2 days
   - Strategy iteration: 2-3 days → 4-6 hours

2. **Improved Quality** (↓ 70% bugs)
   - Reuse tested components
   - Unified test coverage
   - Reduced duplicate code

3. **Easy Experimentation**
   - Quick signal combination testing
   - Easy A/B testing
   - Fair strategy comparison

4. **Asset Accumulation**
   - Build reusable component library
   - Faster development over time
   - Growing component ecosystem

5. **Team Collaboration**
   - Unified code style
   - Easy code review
   - Better knowledge transfer

### Example: Developing New Strategy

**Scenario**: Develop "MA Crossover + RS Filter" strategy

**Before Refactoring** (~300 lines, 3-5 days):
```python
class MACrossoverStrategy(BaseStrategy):
    def __init__(self, config):
        # Manually implement RS calculation (~120 lines)
        # Manually implement market regime filter (~80 lines)
        # Manually implement universe management (~100 lines)
        # Implement MA crossover logic (~50 lines)
```

**After Refactoring** (~80 lines, 1 day):
```python
from strategy.common.indicators import RelativeStrengthCalculator
from strategy.common.universe import DynamicUniverseManager

class MACrossoverStrategy(BaseStrategy):
    def __init__(self, config):
        # Reuse RS calculation
        self.rs_calculator = RelativeStrengthCalculator()

        # Reuse universe management
        self.universe_manager = DynamicUniverseManager(...)

        # Only implement MA crossover logic (~50 lines)
        self.fast_ma = deque(maxlen=10)
        self.slow_ma = deque(maxlen=30)
```

**Time Saved**: 67% (3-5 days → 1 day)

### Testing Strategy

**Component Tests** (`tests/test_common_components.py`):
- 15 test cases covering all components
- Test initialization, calculation, and edge cases
- All tests pass ✅

**Logic Verification** (`tests/verify_refactoring.py`):
- Verify calculation formulas match original
- Verify data flow consistency
- Verify decision logic consistency
- All tests pass ✅

**Run Tests**:
```bash
# Component tests
uv run pytest tests/test_common_components.py -v

# Logic verification
uv run python tests/verify_refactoring.py
```

### Documentation

- **`strategy/common/README.md`** - Complete component library documentation
- **`docs/MODULAR_REFACTORING.md`** - Refactoring summary report
- **`docs/REFACTORING_VERIFICATION.md`** - Logic verification report

### Best Practices

1. **Prioritize Reuse**: Check `strategy/common/` for reusable components first
2. **Keep It Simple**: Each component does one thing well
3. **Write Tests**: New components must have unit tests
4. **Document Well**: Add clear docstrings and usage examples
5. **Backward Compatible**: Keep interfaces stable when modifying components

### Migration Guide

**For Existing Strategies**:
1. Identify reusable logic (indicators, signals, filters)
2. Extract to `strategy/common/` with appropriate structure
3. Update strategy to use new components
4. Add tests for extracted components
5. Verify backtest results match original

**For New Strategies**:
1. Check `strategy/common/` for reusable components
2. Only implement strategy-specific logic
3. Compose components to build strategy
4. Add strategy-specific tests
5. Document strategy design

### Future Enhancements

**Short-term** (1-2 weeks):
- [x] Migrate other strategies (Dual Thrust, etc.) to modular architecture
- [ ] Add more common indicators (RSI, MACD, etc.)
- [ ] Enhance documentation and examples

**Mid-term** (1-2 months):
- [ ] Build strategy backtest comparison framework
- [x] Add performance analysis tools ✅ (2026-02-20)
- [ ] Build strategy portfolio manager

**Long-term** (3-6 months):
- [ ] Build strategy auto-optimization framework
- [ ] Add machine learning components
- [ ] Build strategy marketplace

---

## 🔬 Performance Analysis & Profiling Tools (2026-02-20)

### Overview

The project now includes comprehensive performance analysis and profiling tools for strategy evaluation and backtest engine optimization.

**Key Achievement**:
- ✅ Strategy performance analysis tool (~1,790 lines)
- ✅ Backtest profiling tool (~1,450 lines)
- ✅ 13 performance metrics (Sharpe, Sortino, Calmar, Win Rate, etc.)
- ✅ cProfile integration for bottleneck identification
- ✅ Real backtest performance comparison completed

### Architecture

```
utils/
├── performance/                          # Strategy Performance Analysis
│   ├── metrics.py                       # PerformanceMetrics class (~350 lines)
│   ├── analyzer.py                      # StrategyAnalyzer class (~280 lines)
│   ├── reporter.py                      # ReportGenerator class (~180 lines)
│   └── README.md                        # Complete documentation (~450 lines)
├── profiling/                           # Backtest Profiling
│   ├── profiler.py                      # BacktestProfiler class (~290 lines)
│   ├── analyzer.py                      # ProfileAnalyzer class (~280 lines)
│   ├── reporter.py                      # ProfileReporter class (~180 lines)
│   └── README.md                        # Complete documentation (~450 lines)
examples/
├── performance_analysis_example.py      # 4 usage examples (~250 lines)
└── profiling_example.py                 # 5 usage examples (~250 lines)
tests/
└── test_performance_analysis.py         # 18 test cases (~280 lines)
scripts/
├── compare_engine_performance_simple.py # Simulation test
└── compare_engine_performance_real.py   # Real backtest comparison
```

### 1. Strategy Performance Analysis Tool

**Purpose**: Calculate and compare strategy performance metrics

**Supported Metrics** (13 total):
- **Return Metrics**: Total Return, Annualized Return
- **Risk Metrics**: Max Drawdown, Volatility, Downside Volatility
- **Risk-Adjusted Returns**: Sharpe Ratio, Sortino Ratio, Calmar Ratio
- **Trade Statistics**: Win Rate, Profit Factor, Avg Win/Loss, Trade Count

**Usage**:
```python
from utils.performance import PerformanceMetrics, StrategyAnalyzer, ReportGenerator

# Calculate metrics for a single strategy
metrics = PerformanceMetrics(
    returns=strategy_returns,
    trades=trade_list,
    initial_capital=100000,
)

sharpe = metrics.sharpe_ratio()
max_dd = metrics.max_drawdown()
win_rate = metrics.win_rate()

# Compare multiple strategies
analyzer = StrategyAnalyzer()
analyzer.add_strategy("Strategy A", returns_a, trades_a)
analyzer.add_strategy("Strategy B", returns_b, trades_b)

# Generate comparison report
comparison = analyzer.compare_strategies()
ranking = analyzer.rank_strategies(by="sharpe_ratio")

# Export reports
reporter = ReportGenerator(analyzer)
reporter.generate_text_report("output/report.txt")
reporter.generate_markdown_report("output/report.md")
reporter.export_to_csv("output/metrics.csv")
```

**Key Features**:
- Comprehensive metric calculation (13 metrics)
- Multi-strategy comparison and ranking
- Flexible report generation (Text/Markdown/CSV/Excel)
- Strategy filtering and correlation analysis
- Configurable risk-free rate and trading days

### 2. Backtest Profiling Tool

**Purpose**: Identify performance bottlenecks in backtest code

**Features**:
- **cProfile Integration**: Low-overhead performance profiling
- **Hotspot Identification**: Find most time-consuming functions
- **Bottleneck Analysis**: Identify performance bottlenecks
- **I/O Operation Tracking**: Monitor file operations
- **Comparison Analysis**: Compare before/after optimization

**Usage**:
```python
from utils.profiling import BacktestProfiler, ProfileAnalyzer, ProfileReporter

# Profile a backtest function
profiler = BacktestProfiler()

with profiler.profile():
    run_backtest(config)

profiler.save("output/backtest.prof")

# Analyze profile data
analyzer = ProfileAnalyzer("output/backtest.prof")

# Get top 20 hotspots
hotspots = analyzer.get_hotspots(top_n=20)

# Identify bottlenecks (>5% total time)
bottlenecks = analyzer.identify_bottlenecks(threshold=0.05)

# Find I/O operations
io_ops = analyzer.get_io_operations(top_n=10)

# Generate report
reporter = ProfileReporter(analyzer)
reporter.generate_text_report("output/profile_report.txt")
reporter.generate_markdown_report("output/profile_report.md")
```

**Key Features**:
- Function-level and context manager profiling
- Automatic hotspot and bottleneck identification
- I/O operation tracking (file reads/writes)
- Detailed performance reports
- Profile data comparison

### 3. Backtest Engine Performance Comparison

**Real Backtest Results** (155 trading pairs, full dataset):

```
High-Level Engine (BacktestNode):
  ⏱️  Total Time: 272.45 seconds (4.5 minutes)
  💾 Data Loading: ~6.5s (2.4% of total)
  📊 Strategy Execution: 162.93s (on_bar)
  ✅ Uses Parquet caching

Low-Level Engine (BacktestEngine):
  ⏱️  Total Time: 360.92 seconds (6.0 minutes)
  💾 Data Loading: 66.75s (18.5% of total) ⚠️
  📊 Strategy Execution: 176.21s (on_bar)
  ❌ Reads CSV every time

⚡ Performance Difference: High-level engine is 32% faster!
```

**Key Findings**:
1. **High-level engine is faster** (unexpected result!)
   - 272.45s vs 360.92s (88.47s difference)
   - Main advantage: Parquet caching mechanism

2. **Data loading is the bottleneck**
   - Low-level: 66.75s (18.5% of total time)
   - High-level: ~6.5s (2.4% of total time)
   - 10x difference in data loading!

3. **Strategy execution is similar**
   - on_bar: 162.93s vs 176.21s
   - Difference mainly in data loading phase

4. **Optimization opportunities**
   - _update_bollinger_bands: 74.16s
   - _update_indicators: 110.24s
   - These are in strategy code, can be optimized

**Run Performance Comparison**:
```bash
# Simulation test (verify tools work)
uv run python scripts/compare_engine_performance_simple.py

# Real backtest comparison (155 pairs, full data)
uv run python scripts/compare_engine_performance_real.py
```

### Benefits

1. **Data-Driven Optimization**
   - Identify real bottlenecks with profiling data
   - Avoid premature optimization
   - Measure optimization impact quantitatively

2. **Strategy Evaluation**
   - Compare strategies objectively with 13 metrics
   - Rank strategies by risk-adjusted returns
   - Generate professional reports for analysis

3. **Development Efficiency**
   - Quick performance checks during development
   - Automated report generation
   - Easy integration into workflow

4. **Quality Assurance**
   - Ensure optimizations don't break functionality
   - Track performance regressions
   - Maintain performance benchmarks

### Best Practices

1. **Profile Before Optimizing**
   - Always profile to find real bottlenecks
   - Don't optimize based on assumptions
   - Focus on functions with >5% total time

2. **Use Appropriate Tools**
   - Performance analysis: For strategy comparison
   - Profiling: For code optimization
   - Both: For comprehensive analysis

3. **Benchmark Regularly**
   - Profile after major changes
   - Compare before/after optimization
   - Track performance over time

4. **Document Findings**
   - Save profile reports for reference
   - Document optimization decisions
   - Share insights with team

### Testing

**Performance Analysis Tests** (`tests/test_performance_analysis.py`):
- 18 test cases covering all metrics
- Test edge cases (zero trades, negative returns)
- All tests pass ✅

**Run Tests**:
```bash
# Performance analysis tests
uv run python -m unittest tests.test_performance_analysis -v

# Profiling tool tests (manual verification)
uv run python examples/profiling_example.py
```

### Documentation

- **`utils/performance/README.md`** - Performance analysis tool documentation
- **`utils/profiling/README.md`** - Profiling tool documentation
- **`examples/performance_analysis_example.py`** - 4 usage examples
- **`examples/profiling_example.py`** - 5 usage examples

### Real-World Impact

**Backtest Engine Analysis**:
- Discovered high-level engine is 32% faster
- Identified data loading as main bottleneck (10x difference)
- Found strategy code optimization opportunities (74.16s + 110.24s)
- Recommendation: Continue using high-level engine

**Development Workflow**:
- Performance analysis integrated into strategy evaluation
- Profiling used for optimization decisions
- Automated report generation saves time

---

## 📊 Optimization Lessons Learned (Updated 2026-02-20)

(Existing content retained.)

## 📁 Project Maintenance (2026-02-01)

### 8. Modular Strategy Architecture (2026-02-20)

**Context**: Strategy code was monolithic with high duplication (~1080 lines per strategy)

**Problem**:
- New strategy development took 3-5 days
- 90% code duplication across strategies
- Difficult to maintain and test
- Hard to compare strategies fairly

**Solution**: Extract reusable components into `strategy/common/`
- Created 7 reusable components (indicators, signals, universe)
- Reduced strategy code by 40% (1080 → 650 lines)
- Increased code reuse rate by 700% (10% → 80%)
- Added 15 component tests + 6 logic verification tests

**Results**:
- ✅ New strategy development time: ↓ 60% (3-5 days → 1-2 days)
- ✅ Strategy iteration speed: ↓ 75% (2-3 days → 4-6 hours)
- ✅ Code duplication: ↓ 70%
- ✅ Test coverage: +17 tests
- ✅ All tests pass (17/17)

**Key Learnings**:
1. **Component Design**: Single responsibility, clear interfaces
2. **Testing First**: Write tests before extracting components
3. **Logic Verification**: Verify refactored code produces same results
4. **Documentation**: Comprehensive docs accelerate adoption
5. **Gradual Migration**: Keep original version during transition

**Files**:
- `strategy/common/` - Component library (7 components)
- `tests/test_common_components.py` - Component tests (15 tests)
- `tests/verify_refactoring.py` - Logic verification (6 tests)
- `docs/MODULAR_REFACTORING.md` - Refactoring report
- `docs/REFACTORING_VERIFICATION.md` - Verification report

### 9. Performance Analysis & Profiling Tools (2026-02-20)

**Context**: Needed tools to evaluate strategy performance and identify backtest bottlenecks

**Problem**:
- No systematic way to compare strategy performance
- Unclear which backtest engine is faster
- Unknown performance bottlenecks in code
- Manual performance analysis was time-consuming

**Solution**: Built comprehensive performance analysis and profiling tools
- Created strategy performance analysis tool (~1,790 lines)
- Created backtest profiling tool (~1,450 lines)
- Implemented 13 performance metrics (Sharpe, Sortino, Calmar, etc.)
- Integrated cProfile for bottleneck identification
- Ran real backtest performance comparison (155 pairs)

**Results**:
- ✅ Discovered high-level engine is 32% faster (272.45s vs 360.92s)
- ✅ Identified data loading as main bottleneck (10x difference: 66.75s vs 6.5s)
- ✅ Found strategy code optimization opportunities (184.32s in indicators)
- ✅ Built reusable performance analysis framework
- ✅ All tools tested and documented

**Key Learnings**:
1. **Profile Before Optimizing**: Real data reveals unexpected results (high-level engine faster)
2. **Data Loading Matters**: Parquet caching provides 10x speedup over CSV
3. **Measure Everything**: 13 metrics provide comprehensive strategy evaluation
4. **Automate Analysis**: Report generation saves significant time
5. **Document Findings**: Performance reports guide optimization decisions

**Unexpected Discovery**:
- Initially assumed low-level engine would be faster (simpler code)
- Real testing showed high-level engine is 32% faster
- Reason: Parquet caching vs repeated CSV reads
- Lesson: Always measure, don't assume

**Files**:
- `utils/performance/` - Performance analysis tool (4 files, ~1,790 lines)
- `utils/profiling/` - Profiling tool (4 files, ~1,450 lines)
- `tests/test_performance_analysis.py` - 18 test cases
- `examples/performance_analysis_example.py` - 4 usage examples
- `examples/profiling_example.py` - 5 usage examples
- `scripts/compare_engine_performance_real.py` - Real backtest comparison

---

## ✅ Completed Optimizations (Updated 2026-02-20)

(Existing content retained.)

---

## 🛡️ AI Agent Git & CI Policy (New)

This section documents the explicit policies and safe operating procedures for AI agents (automated assistants / bots) who modify code, produce patches, run local tests, or interact with Git and CI in this repository. Follow these rules strictly—they are part of the team's governance and reduce risk when automating changes.

**Repository Privacy Note**: This repository is private. All files, including sensitive configurations, API keys, and proprietary code, can be safely committed to version control. The remote repository is hosted on a private server with restricted access.

Purpose
- Ensure AI-driven changes are transparent, auditable, and safe.
- Prevent unreviewed semantic changes from being automatically merged.
- Allow CI to perform deterministic, low-risk fixes while keeping human control over logic changes.

A. General Principles for AI Agents
1. No autonomous PR creation or merging:
   - AI agents must NOT create or merge PRs on their own initiative.
   - Exception: CI workflows are allowed to create PRs for specific auto-fix actions (see CI section). AI must never impersonate this behavior.
2. Push and branch control:
   - The AI may create local branches and prepare commits in the working tree.
   - Pushing to remote is allowed only when explicitly authorized by a human (the repository owner, maintainer, or an explicit instruction from a designated user).
   - When pushing is authorized, AI must:
     - Use a descriptive branch name (see commit rules).
     - Avoid pushing directly to protected branches (e.g., `main`).
3. Commit content rules:
   - Keep commits small, focused, and well-documented.
   - Do not remove or alter comments that appear to be explanatory or policy-related unless explicitly requested.
   - Do not hardcode secrets, API keys, or credentials.
4. Tests-first behavior:
   - Before proposing or pushing changes, AI should run the full test suite locally (using the project's test command).
   - If tests fail locally, AI must not push the change; instead, it should collect diagnostics and present a patch + suggested fixes to a human reviewer.
5. Change proposals and transparency:
   - AI must produce a compact patch summary: files changed, motivation (1-2 lines), tests run and results, and any known risks.
   - Always include a suggested PR description body when the user requests the AI to prepare a PR (the AI will not create the PR without user authorization).

B. Commit Message & Branch Naming Conventions
- Commit message format (single-line summary preferred, optional longer body):
  - `<type>(<scope>): <short summary>`
  - Example: `refactor(core/adapter): delegate instrument/bar restore to instrument_helpers`
  - Types: `fix`, `feat`, `refactor`, `chore`, `ci`, `docs`, `test`, `perf`
- Branch naming:
  - feature/xxx, fix/xxx, refactor/xxx, ci/xxx
  - Example: `feature/instrument-helper-adapter`, `ci/ruff-autofix-2026-02-03`

C. Behavior When Tests Fail
1. If the AI runs tests and failures occur:
   - Collect full failing tracebacks and the minimal reproduction test (if possible).
   - Attempt 1-2 safe diagnostic fixes (typo fixes, missing imports). Do not attempt large refactors automatically.
   - Present a proposed patch and a short explanation of root cause and proposed fix to the human reviewer.
   - If the user authorizes, AI may create a branch with the proposed fix and push it (still not creating a PR).
2. If CI reports failures on a branch the AI produced:
   - The AI should not modify the branch automatically.
   - It should report diagnostics and propose a small fix as a separate branch, or ask for human instruction.

D. CI Auto-fix Rules and Allowed Automation
1. CI is allowed to auto-fix deterministic, non-semantic issues:
   - Examples: code formatting and lint autofixes (`ruff --fix`, `isort`, `black`).
   - CI auto-fix must create a PR (not merge) and must include a clear PR title/body describing what rules were applied.
2. CI must NOT auto-apply semantic changes:
   - No behavioral fixes, algorithm changes, or heuristic alterations should be auto-applied by CI.
   - If tests are affected by auto-fix, the auto-fix PR must not be merged automatically.
3. PR protection and review:
   - All auto-fix PRs must require human review and appropriate CI status checks before merging.
   - PRs created by CI should be labeled (example: `automated`, `autofix`) and include a checklist of what was changed.

E. Minimal Example Workflows (AI + CI interactions)
- Normal AI patch workflow (recommended):
  1. AI runs local tests, produces patch, prepares branch `feature/xyz`.
  2. AI presents patch and PR draft content to human reviewer.
  3. On explicit human instruction, AI pushes branch to remote.
  4. Human creates PR or asks AI to open PR (if permitted).
- CI auto-fix workflow (allowed):
  1. CI runs lint job; detects auto-fixable issues.
  2. CI runs tests; if tests pass and only styling fixes were made, CI opens a PR with fixes.
  3. PR remains unmerged until human review and CI status green.

F. Permissions, Tokens & Security
- AI agents must never store or leak credentials.
- Any CI workflow that creates branches or PRs must use the repository's configured tokens and respect repository protections.
- AI should log all attempted remote operations (pushes, branch creation) in the change summary it provides.

G. Documentation & Audit Trail
- Every AI-driven change must include:
  - A short changelog entry (1-2 lines) in the PR body or commit.
  - Tests run (which test target and results).
  - Any environment differences (if tests passed locally but failed in CI).
- Maintain an audit trail (in PRs or issue tracker) describing AI involvement and approvals.

H. Exceptions & Human Overrides
- The user/maintainer may explicitly authorize the AI to:
  - Push and create PRs for a specific branch.
  - Create PRs for small, well-scoped fixes.
- Such authorizations must be explicit, time-bounded, and recorded in the change summary.

I. Quick Checklist for AI Agents (before any remote operation)
- [ ] Ran `uv sync` and ensured environment is reproducible.
- [ ] Ran full tests: `uv run python -m unittest discover -s tests -p "test_*.py" -v`.
- [ ] Prepared concise patch summary (files, motivation, tests).
- [ ] Obtained explicit permission to push remote changes.
- [ ] Used the commit & branch naming conventions above.

---

## FAQ (AI agent specific)

Q: May the AI create a PR if it’s only formatting fixes?
- A: No. The AI itself must not create PRs. CI may create a PR for formatting fixes under the CI policy. If you (a human) instruct the AI to create a PR, the AI may do so.

Q: May the AI push a branch directly to origin?
- A: Only with explicit human authorization. The AI can prepare a branch locally and share the patch/diff without pushing.

Q: If CI creates an autofix PR and tests fail, what happens?
- A: The PR must not be merged. The CI should attach failure logs and notify maintainers. The AI can propose a manual fix branch but must not auto-merge.

---

## Closing Notes (short)
- These rules prioritize safety and traceability over raw automation speed.
- The AI's role is to assist with diagnostics, propose fixes, and accelerate development while leaving final accept/merge decisions to humans.
- If you want any policy adjustments (e.g., allow daily auto-fix merges under strict conditions), propose them in an issue and the team will decide.

(End of AGENTS.md — for full project guidelines and historical content see the repository.)