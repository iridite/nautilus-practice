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

## 📊 Optimization Lessons Learned (2026-02-01)

(Existing content retained.)

## 📁 Project Maintenance (2026-02-01)

(Existing content retained.)

## ✅ Completed Optimizations (2026-02-01)

(Existing content retained.)

---

## 🛡️ AI Agent Git & CI Policy (New)

This section documents the explicit policies and safe operating procedures for AI agents (automated assistants / bots) who modify code, produce patches, run local tests, or interact with Git and CI in this repository. Follow these rules strictly—they are part of the team's governance and reduce risk when automating changes.

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