# Nautilus Practice - 量化交易策略开发平台

基于 NautilusTrader 框架的加密货币量化交易策略开发和回测平台。

## 🚀 项目概述

**Nautilus Practice** 是一个专业的量化交易项目，专注于加密货币永续合约的策略开发、回测和实盘交易。项目基于强大的 NautilusTrader 框架构建，提供完整的策略开发工具链。

### 核心特性

- ✅ **多策略支持**: OI Divergence、RS Squeeze、Dual Thrust 等策略实现
- ✅ **双回测引擎**: 低级别直接API和高级别Parquet目录支持
- ✅ **自定义数据**: Open Interest、Funding Rate 等衍生品数据集成
- ✅ **全自动OI数据获取**: 智能检查和自动下载OI/Funding Rate数据 🆕
- ✅ **策略数据依赖声明**: 声明式数据需求管理 🆕
- ✅ **多交易所**: 支持 Binance、OKX 等主流交易所
- ✅ **完整测试**: 106个单元测试确保代码质量
- ✅ **模块化架构**: 重构后的工具模块消除代码重复

## 🛠️ 技术栈

- **Framework**: NautilusTrader (nautilus-trader)
- **Python**: 3.12.12+ (严格要求 `>=3.12.12, <3.13`)
- **Package Manager**: `uv` (现代Python包管理器)
- **Domain**: 加密货币量化交易 (永续合约)
- **Exchanges**: Binance, OKX

## 📦 安装和环境配置

### 前置要求

- Python 3.12.12+
- uv package manager
- Git

### 快速开始

```bash
# 1. 克隆仓库
git clone <repository-url>
cd nautilus-practice

# 2. 安装依赖
uv sync

# 3. 激活虚拟环境（可选）
source .venv/bin/activate

# 4. 运行测试验证安装
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 5. 快速开始 - 运行带OI数据的回测
uv run python main.py backtest
```

### 🚀 快速开始指南

```bash
# 1. 基本回测（自动获取所有需要的数据）
uv run python main.py backtest

# 2. 查看OI策略示例
uv run python examples/oi_strategy_example.py

# 3. 测试OI数据集成功能
uv run python test_oi_integration.py
```

**首次运行**: 系统会自动检测策略的数据需求，并从交易所下载所需的OI和Funding Rate数据。这个过程可能需要几分钟时间，取决于数据量和网络状况。

### 环境变量配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件，添加API密钥等
# 注意：不要提交包含真实密钥的文件到版本控制
```

## 🔧 使用指南

### 运行回测

```bash
# 主回测入口（自动检查和获取所有数据）
uv run python main.py backtest

# 跳过OI数据检查（仅使用OHLCV数据）
uv run python main.py backtest --skip-oi-data

# 强制重新下载所有OI数据
uv run python main.py backtest --force-oi-fetch

# 指定首选交易所和重试次数
uv run python main.py backtest --oi-exchange binance --max-retries 5

# 特定策略回测
uv run python backtest/backtest_oi_divergence.py

# 数据准备脚本
uv run python scripts/prepare_oi_divergence_data.py
```

### 🆕 OI数据自动获取功能

系统现在支持全自动的Open Interest和Funding Rate数据管理：

#### 新增命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--skip-oi-data` | 跳过OI数据检查和获取 | False |
| `--force-oi-fetch` | 强制重新下载所有OI数据 | False |
| `--oi-exchange` | 指定首选交易所 (binance/okx/auto) | auto |
| `--max-retries` | 设置最大重试次数 | 3 |

#### 智能数据管理特性

- **自动检测**: 根据策略配置自动识别所需的OI和Funding Rate数据
- **增量下载**: 仅下载缺失的数据文件，避免重复下载
- **多交易所支持**: 主交易所失败时自动切换到备用交易所
- **智能重试**: 网络失败时自动重试，支持渐进式延迟
- **数据验证**: 自动验证数据完整性和质量

### 数据准备

```bash
# 生成交易对Universe
uv run python scripts/generate_universe.py

# 准备Top市值数据
uv run python scripts/prepare_top_data.py

# 获取工具信息
uv run python scripts/fetch_instrument.py
```

### 运行测试

```bash
# 运行所有测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 运行单个测试文件
uv run python -m unittest tests/test_oi_divergence.py -v

# 运行特定测试类
uv run python -m unittest tests.test_oi_divergence.TestCustomData -v
```

## 📁 项目结构

```
nautilus-practice/
├── strategy/              # 📈 交易策略实现
│   ├── base.py           #     基础策略类
│   ├── oi_divergence_strategy.py  #     OI背离策略
│   ├── rs_squeeze.py     #     RS挤压策略
│   └── dual_thrust.py    #     双推力策略
├── utils/                # 🛠️ 工具模块 (新架构)
│   ├── __init__.py       #     统一导入接口
│   ├── time_helpers.py   #     时间处理工具
│   ├── network.py        #     网络重试工具
│   ├── validation.py     #     数据验证工具
│   ├── symbol_parser.py  #     符号解析工具
│   ├── data_loader.py    #     数据加载工具
│   ├── path_helpers.py   #     路径操作工具
│   ├── config_helpers.py #     配置解析工具
│   ├── custom_data.py    #     自定义数据类型
│   └── oi_funding_adapter.py   #     OI/Funding数据适配器
├── backtest/             # 🔬 回测引擎
│   ├── engine_low.py     #     低级别回测引擎
│   ├── engine_high.py    #     高级别回测引擎
│   └── exceptions.py     #     异常定义
├── tests/                # 🧪 单元测试
├── scripts/              # 📜 工具脚本
├── config/               # ⚙️ 配置文件
├── data/                 # 📊 市场数据 (gitignored)
├── docs/                 # 📚 文档
│   └── utils_guide.md    #     工具模块使用指南
└── main.py               # 🚪 主入口
```

## 🆕 工具模块架构 (重构亮点)

项目经过全面重构，消除了代码重复，建立了模块化的工具架构：

### 统一导入接口

```python
# 推荐：通过统一接口导入
from utils import (
    get_ms_timestamp,      # 时间处理
    retry_fetch,           # 网络重试
    check_data_exists,     # 数据验证
    resolve_symbol_and_type,  # 符号解析
    load_csv_with_time_detection,  # 数据加载
    get_project_root,      # 路径操作
    load_universe_symbols_from_file  # 配置解析
)
```

### 模块化设计

| 模块 | 功能 | 主要函数 |
|------|------|----------|
| `time_helpers` | 时间处理 | `get_ms_timestamp()` |
| `network` | 网络重试 | `retry_fetch()` |
| `validation` | 数据验证 | `check_data_exists()` |
| `symbol_parser` | 符号解析 | `resolve_symbol_and_type()`, `parse_timeframe()` |
| `data_loader` | 数据加载 | `load_csv_with_time_detection()` |
| `path_helpers` | 路径操作 | `get_project_root()` |
| `config_helpers` | 配置解析 | `load_universe_symbols_from_file()` |

**详细使用指南**: 📖 [工具模块使用指南](docs/utils_guide.md)

## 🏗️ 回测引擎

### 1. 低级别引擎 (`backtest/engine_low.py`)
- 直接使用 BacktestEngine API
- 完全控制回测过程
- 适合高级用户和自定义需求

### 2. 高级别引擎 (`backtest/engine_high.py`)  
- 使用 BacktestNode 和 Parquet 目录
- 简化配置和使用
- 适合快速策略验证

### 重要注意事项
- ⚠️ CSV数据文件必须使用 "datetime" 或 "timestamp" 作为时间列名
- ⚠️ 高级别引擎默认期望 "datetime" 列
- ✅ 两个引擎都已在 NautilusTrader 1.223.0 验证工作正常

## 📈 策略开发

### 基础策略结构

所有策略都继承自 `BaseStrategy` 并实现：

```python
from strategy.base import BaseStrategy, BaseStrategyConfig

class MyStrategyConfig(BaseStrategyConfig):
    # 策略特定参数
    lookback_bars: int = 48
    entry_threshold: float = 0.05

class MyStrategy(BaseStrategy):
    def on_start(self):
        """初始化指标和验证配置"""
        super().on_start()
        # 初始化逻辑
        
    def on_bar(self, bar):
        """处理Bar数据和交易逻辑"""
        # 交易逻辑
        
    def on_data(self, data):
        """处理自定义数据 (OI, funding rates)"""
        # 自定义数据处理
```

### 🆕 策略数据依赖声明

新的数据依赖声明机制让策略可以明确声明所需的数据类型：

```python
from strategy.base import BaseStrategy, BaseStrategyConfig

class MyStrategyConfig(BaseStrategyConfig):
    def __init__(self):
        super().__init__()
        
        # 声明必需的OI数据依赖
        self.add_data_dependency(
            data_type="oi",
            required=True,
            period="1h",
            exchange="binance",
            auto_fetch=True
        )
        
        # 声明必需的Funding Rate数据依赖
        self.add_data_dependency(
            data_type="funding",
            required=True,
            exchange="binance",
            auto_fetch=True
        )
        
        # 可选的备用数据源
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
        
        # 检查数据依赖状态
        if self.base_config.has_oi_dependency():
            self.log.info("Strategy requires OI data")
        
        if self.base_config.has_funding_dependency():
            self.log.info("Strategy requires Funding Rate data")
```

### 现有策略

1. **OI Divergence Strategy**: 基于持仓量背离的趋势策略
2. **RS Squeeze Strategy**: 基于相对强度挤压的突破策略
3. **Dual Thrust Strategy**: 经典的双推力突破策略

**示例**: 查看 [`examples/oi_strategy_example.py`](examples/oi_strategy_example.py) 了解完整的数据依赖声明用法

## 📊 数据管理

### 支持的数据类型

- **OHLCV**: 标准K线数据
- **Open Interest**: 持仓量数据
- **Funding Rate**: 资金费率数据
- **自定义数据**: 扩展的市场数据类型

### 数据获取

```python
# 使用重构后的工具模块
from utils import batch_fetch_ohlcv, get_ms_timestamp

# 批量获取OHLCV数据
configs = batch_fetch_ohlcv(
    symbols=["BTCUSDT", "ETHUSDT"],
    start_date="2024-01-01",
    end_date="2024-12-31", 
    timeframe="1h",
    exchange_id="binance",
    base_dir=Path(".")
)
```

## 🧪 测试框架

项目包含106个全面的单元测试：

```bash
# 运行所有测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 测试覆盖范围
- 自定义数据类型测试
- 策略逻辑测试  
- 工具模块测试
- 回测引擎测试
- 数据加载测试
```

## ⚡ 性能优化

- **缓存机制**: `get_project_root()` 内置缓存
- **批量操作**: 支持批量数据检查和处理
- **智能重试**: 网络请求智能延迟策略
- **内存优化**: 高效的数据加载和处理

## 🔒 安全注意事项

- 🔑 API密钥存储在 `.env` 文件中 (已在 `.gitignore`)
- 🚫 永远不要提交包含真实密钥的文件
- 🔐 使用环境特定的配置文件 (`live.env`, `test.env`)

## 🤝 贡献指南

### 代码风格

项目遵循严格的代码规范:

- **类型注解**: 所有函数都需要完整的类型注解
- **现代语法**: 使用 Python 3.12+ 联合类型语法 (`int | None`)
- **金融精度**: 财务计算必须使用 `Decimal` 而不是 `float`
- **文档字符串**: 详细的参数说明，支持中英文混合

### 添加新功能

1. 选择合适的模块或创建新模块
2. 遵循命名约定 (`snake_case`)
3. 添加完整的类型注解和文档字符串
4. 创建对应的单元测试
5. 更新统一导入接口

详细指南请参考: [AGENTS.md](AGENTS.md)

## 📚 文档

- 📖 [工具模块使用指南](docs/utils_guide.md)
- 📝 [代码开发规范](AGENTS.md)
- 🆕 [OI数据使用指南](docs/oi_data_usage_guide.md)
- 📊 [OI Divergence策略文档](docs/oi_divergence_strategy.md)
- 📊 [策略文档](docs/)
- 🧪 [测试指南](tests/)
- 📋 [OI数据集成报告](docs/AI%20Exec%20Reports/OI_DATA_INTEGRATION_REPORT.md)

## 📞 支持

遇到问题时:

1. 检查单元测试中的使用示例
2. 查看源代码中的文档字符串  
3. 运行测试验证功能是否正常
4. 查阅相关文档

## 🎯 TODO

- 研究下，在回测过程中的极大负净值能不能在现实中可行

---

**版本**: v2.1 🆕
**更新时间**: 2026-01-23
**新增功能**: 全自动OI数据获取和策略数据依赖声明
**作者**: Roo AI Assistant
**Framework**: NautilusTrader 1.223.0
