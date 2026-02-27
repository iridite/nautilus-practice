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
├── strategy/              # 策略实现
│   ├── common/           # 可复用组件
│   │   ├── indicators/   # 技术指标
│   │   ├── signals/      # 信号生成器
│   │   └── universe/     # 标的选择
│   └── *.py              # 策略实现
├── backtest/             # 回测引擎
├── config/               # 配置文件
│   ├── strategies/       # 策略配置
│   └── environments/     # 环境配置
├── core/                 # 核心配置系统
├── utils/                # 工具模块
├── data/                 # 数据目录
├── docs/                 # 文档
│   └── lessons-learned/  # 经验教训
└── tests/                # 测试
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

# 运行回测（推荐高级引擎）
uv run python main.py backtest --type high

# 分析回测结果
python scripts/analyze_backtest_results.py

# 查看最新结果
ls -lht output/backtest/result/*.json | head -3
```

## 核心功能

### 1. 模块化策略架构

- 可复用组件：指标、信号、Universe
- 策略代码减少 40%
- 代码复用率提升 700%

### 2. 双回测引擎

- **低级引擎**: 简单、直接、易调试
- **高级引擎**: 快 32%、Parquet 缓存、10x 数据加载速度

### 3. TUI 终端界面

- 实时进度显示
- 统一日志管理
- 清晰的数据处理总结

### 4. 性能分析工具

- 13 个性能指标（Sharpe、Sortino、Calmar 等）
- cProfile 集成
- 自动化报告生成

### 5. 过滤器诊断系统

- 详细的过滤器统计
- 自动零交易警告
- 优化建议

## 文档

详细文档位于 `docs/lessons-learned/`:

- [架构决策记录](docs/lessons-learned/ARCHITECTURE_DECISIONS.md) - 模块化、性能优化、配置简化
- [TUI 集成经验](docs/lessons-learned/TUI_INTEGRATION.md) - 终端界面实现和生命周期管理
- [Git 工作流](docs/lessons-learned/GIT_WORKFLOW.md) - 分支管理、Commit 规范、CI/CD
- [策略调试与诊断](docs/lessons-learned/STRATEGY_DEBUGGING.md) - 零交易诊断、过滤器优化

其他文档：
- `CLAUDE.md`: AI Agent 开发指南
- `docs/BINANCE_API_SETUP.md`: Binance API 配置
- `docs/OKX_TESTNET_SETUP.md`: OKX 测试网配置
- `docs/guides/`: 策略开发指南

## 注意事项

1. CSV 数据文件必须使用 "datetime" 或 "timestamp" 作为时间列名
2. **优先使用高级引擎**：比低级引擎快 32%，且提供完整统计数据
3. 金融计算使用 `Decimal` 而非 `float`
4. Python 版本严格要求 3.12.12+，不支持 3.13
5. **参数调优在独立分支进行**：策略优化工作应在 `feat/strategy-optimization` 等独立分支进行，避免污染 main 分支

## 常见问题

### Q: 回测产生 0 交易？

A: 使用过滤器诊断系统：
1. 启用 DEBUG 日志：`level: "DEBUG"`
2. 关闭 components_only：`components_only: false`
3. 查看过滤器统计报告
4. 根据建议调整配置

**常见原因**：
- `keltner_trigger_multiplier` 过小（建议 2.0-2.3）
- `deviation_threshold` 过小（建议 0.30-0.35）
- 过滤器组合效应导致信号被完全拦截

### Q: 数据加载很慢？

A: 使用 Parquet 缓存：
1. 首次运行会生成缓存
2. 后续运行速度提升 10x
3. 缓存位置：`data/parquet/`

### Q: 低级引擎回测结果为空？

A: 低级引擎可能不会生成完整的统计数据：
1. 优先使用高级引擎：`--type high`
2. 高级引擎提供完整的 PNL 和收益率统计
3. 低级引擎主要用于调试和验证

### Q: 如何分析���测结果？

A: 使用分析脚本：
```bash
# 查看所有回测结果排名
python scripts/analyze_backtest_results.py

# 查看最新结果
ls -lht output/backtest/result/*.json | head -3
```

## 许可证

MIT
