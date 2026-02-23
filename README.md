# Nautilus Practice

加密货币量化交易策略开发和回测平台，基于 NautilusTrader 框架。

## 技术栈

- **框架**: NautilusTrader 1.223.0
- **Python**: 3.12.12+ (严格要求 `>=3.12.12, <3.13`)
- **包管理器**: uv
- **交易所**: Binance, OKX

## 快速开始

```bash
# 安装依赖
uv sync

# 运行回测（推荐使用高级引擎）
uv run python main.py backtest --type high

# 运行测试
uv run python -m unittest discover -s tests -p "test_*.py" -v
```

## 当前策略

- **Keltner RS Breakout**: 基于 Keltner 通道和相对强度的突破策略
- **Dual Thrust**: 经典的日内突破策略

## 项目结构

```
nautilus-practice/
├── strategy/           # 策略实现
├── backtest/          # 回测引擎
├── config/            # 配置文件
├── core/              # 核心配置系统
├── utils/             # 工具模块
├── data/              # 数据目录
└── tests/             # 测试
```

## 配置

配置文件位于 `config/` 目录：
- `active.yaml`: 选择当前活跃的策略和环境
- `strategies/`: 各策略的参数配置
- `environments/`: 环境配置（dev/prod）

## 数据管理

数据文件存储在 `data/` 目录：
- `raw/`: 原始 OHLCV 数据（CSV 格式）
- `parquet/`: Parquet 缓存（高级引擎使用）
- `universe/`: 动态交易标的列表

## 常用命令

```bash
# 代码检查
uv run ruff check .
uv run ruff format .

# 运行特定策略回测
uv run python backtest/backtest_keltner_rs.py

# 查看回测结果
ls -lh output/backtest/result/
```

## 注意事项

1. CSV 数据文件必须使用 "datetime" 或 "timestamp" 作为时间列名
2. 高级引擎比低级引擎快 32%，优先使用高级引擎
3. 金融计算使用 `Decimal` 而非 `float`
4. Python 版本严格要求 3.12.12+，不支持 3.13

## 文档

- `CLAUDE.md`: AI Agent 开发指南
- `docs/BINANCE_API_SETUP.md`: Binance API 配置
- `docs/OKX_TESTNET_SETUP.md`: OKX 测试网配置
- `docs/guides/`: 策略开发指南