# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于NautilusTrader框架的加密货币量化交易策略开发和回测平台，专注于永续合约交易。

- **Framework**: NautilusTrader 1.223.0
- **Python**: 3.12.12+ (严格要求 `>=3.12.12, <3.13`)
- **Package Manager**: `uv`
- **Exchanges**: Binance, OKX

## 核心命令

### 环境和依赖
```bash
# 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate
```

### 运行回测
```bash
# 主回测入口（自动获取OI数据）
uv run python main.py backtest

# 跳过OI数据检查
uv run python main.py backtest --skip-oi-data

# 强制重新下载OI数据
uv run python main.py backtest --force-oi-fetch

# 指定交易所和重试次数
uv run python main.py backtest --oi-exchange binance --max-retries 5
```

### 测试
```bash
# 运行所有测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 运行单个测试文件
uv run python -m unittest tests/test_oi_divergence.py -v

# 运行特定测试类
uv run python -m unittest tests.test_oi_divergence.TestCustomData -v
```

### 数据准备
```bash
# 生成交易对Universe
uv run python scripts/generate_universe.py

# 准备Top市值数据
uv run python scripts/prepare_top_data.py

# 获取工具信息
uv run python scripts/fetch_instrument.py
```

## 架构要点

### 双回测引擎架构

项目实现了两个独立的回测引擎，适用于不同场景：

1. **Low-Level Engine** (`backtest/engine_low.py`)
   - 直接使用BacktestEngine API
   - 完全控制回测流程
   - 适合高级用户和自定义需求
   - 手动加载数据和配置

2. **High-Level Engine** (`backtest/engine_high.py`)
   - 使用BacktestNode和Parquet目录
   - 简化配置和使用
   - 适合快速策略验证
   - 自动化数据管理

**重要**: CSV数据文件必须使用"datetime"或"timestamp"作为时间列名。

### 策略架构

所有策略继承自`BaseStrategy`并实现核心生命周期方法：

```python
class MyStrategy(BaseStrategy):
    def on_start(self):
        """初始化指标和验证配置"""
        super().on_start()  # 必须调用

    def on_bar(self, bar):
        """处理Bar数据和交易逻辑"""

    def on_data(self, data):
        """处理自定义数据（OI, funding rates）"""
```

**配置类**继承自`BaseStrategyConfig`：
- 提供统一的仓位管理（`qty_percent`, `leverage`）
- 风险管理参数（`stop_loss_pct`, `use_auto_sl`）
- ATR风险模式（`use_atr_position_sizing`）
- 数据依赖声明（`data_types`列表）

### 数据依赖声明机制

策略通过配置类声明所需数据类型，系统自动检查和获取：

```python
class MyStrategyConfig(BaseStrategyConfig):
    def __init__(self):
        super().__init__()
        self.add_data_dependency(
            data_type="oi",           # 数据类型：oi/funding
            required=True,            # 是否必需
            period="1h",              # 时间周期
            exchange="binance",       # 交易所
            auto_fetch=True           # 自动获取
        )
```

系统在回测前自动：
1. 检查策略的`data_types`列表
2. 验证数据文件是否存在
3. 自动下载缺失的OI/Funding Rate数据
4. 支持多交易所备用和智能重试

### 工具模块统一接口

`utils/`模块提供标准化工具函数，消除代码重复：

```python
from utils import (
    get_ms_timestamp,      # 时间处理
    retry_fetch,           # 网络重试
    check_data_exists,     # 数据验证
    parse_timeframe,       # 符号解析
    load_ohlcv_csv,        # 数据加载
    get_project_root,      # 路径操作
    parse_universe_symbols # 配置解析
)
```

**模块组织**：
- `time_helpers`: 时间戳转换和处理
- `network`: HTTP请求和重试机制
- `validation`: 数据文件验证和检查
- `symbol_parser`: 交易对符号解析和转换
- `data_loader`: CSV数据加载和时间列检测
- `path_helpers`: 项目路径管理（带缓存）
- `config_helpers`: Universe配置解析

### 自定义数据类型

扩展NautilusTrader的数据系统以支持衍生品数据：

- **OpenInterestData**: 持仓量数据
- **FundingRateData**: 资金费率数据

通过`utils.custom_data`和`utils.oi_funding_adapter`模块实现数据加载和适配。

## 关键开发规范

### 类型和精度
- **必须使用类型注解**：所有函数签名和类属性
- **现代语法**：使用`int | None`而非`Optional[int]`
- **金融精度**：价格、数量、百分比必须使用`Decimal`，禁止使用`float`

```python
from decimal import Decimal

def calculate_position_size(
    equity: Decimal,
    price: Decimal,
    percentage: Decimal,
) -> Decimal:
    return (equity * percentage) / price
```

### 导入顺序
遵循PEP 8：
1. 标准库
2. 第三方库（按字母顺序）
3. 本地模块（按字母顺序）

### 命名约定
- 类：PascalCase（`OIDivergence`, `BaseStrategy`）
- 函数/方法：snake_case（`calculate_position_size`, `on_bar`）
- 常量：UPPER_SNAKE_CASE（`START_DATE`, `MAX_POSITIONS`）
- 私有方法：前缀下划线（`_is_ready`, `_update_levels`）

### 常见陷阱

1. **禁止使用float进行金融计算** - 始终使用`Decimal`
2. **必须调用`super().on_start()`** - 在策略初始化时
3. **CSV时间列命名** - 必须是"datetime"或"timestamp"
4. **不要硬编码路径** - 使用`Path(__file__).parent`或`get_project_root()`
5. **环境变量** - API密钥存储在`.env`（已在`.gitignore`）

## 特殊配置

### NautilusTrader包源
项目使用自定义包索引：
```toml
[[tool.uv.index]]
name = "nautilus"
url = "https://packages.nautechsystems.io/simple"
```

允许预发布版本以支持alpha/dev版本。

### 数据文件管理
- `data/`目录已在`.gitignore`中
- 首次运行前需要执行数据准备脚本
- 系统支持自动OI数据获取（通过`main.py backtest`）

## 测试框架

使用Python标准库`unittest`：
- 测试文件：`test_*.py`
- 测试类：`Test<FeatureName>`
- 106个单元测试覆盖核心功能
- 包含自定义数据、策略逻辑、工具模块、回测引擎测试

## 项目结构关键点

```
nautilus-practice/
├── strategy/          # 策略实现（继承BaseStrategy）
│   └── base.py       # 基础策略类和配置
├── backtest/         # 双回测引擎
│   ├── engine_low.py # 低级别引擎
│   └── engine_high.py# 高级别引擎
├── utils/            # 工具模块（统一接口）
│   ├── __init__.py   # 统一导入接口
│   ├── custom_data.py# 自定义数据类型
│   └── oi_funding_adapter.py # OI/Funding数据适配器
├── config/           # 配置文件和适配器
├── scripts/          # 数据准备和工具脚本
├── tests/            # 单元测试（unittest）
└── main.py           # 主入口（支持自动OI数据获取）
```

## 重要注意事项

1. **Python版本严格要求**：`>=3.12.12, <3.13`
2. **中英文混合**：代码注释和文档支持中英文
3. **无自动化linting**：手动遵循PEP 8规范
4. **数据依赖自动化**：策略声明数据需求，系统自动获取
5. **双引擎选择**：根据需求选择Low-Level或High-Level引擎
6. **不生成文档**：不要创建 markdown 报告文档，直接在终端输出即可
