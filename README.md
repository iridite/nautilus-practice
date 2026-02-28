# Nautilus Practice

加密货币量化交易策略开发和回测平台，基于 NautilusTrader 框架。

## 特性

- 🚀 **高性能回测引擎**：Parquet 缓存，数据加载速度提升 10x，回测速度提升 32%
- 📊 **动态标的池（Universe）**：自动生成交易标的，支持周度/月度更新
- 🎯 **模块化策略架构**：可复用组件，代码减少 40%，复用率提升 700%
- 🖥️ **TUI 终端界面**：实时进度显示，统一日志管理
- 📈 **完整性能分析**：13 个性能指标，自动化报告生成
- 🔍 **过滤器诊断系统**：零交易警告，优化建议

## 技术栈

- **框架**: NautilusTrader 1.223.0
- **Python**: 3.12.12+ (严格要求 `>=3.12.12, <3.13`)
- **包管理器**: uv
- **交易所**: Binance, OKX

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/iridite/nautilus-practice.git
cd nautilus-practice

# 安装依赖
uv sync
```

### 运行回测

```bash
# 使用高级引擎（推荐）
uv run python main.py backtest --type high

# 使用低级引擎（调试用）
uv run python main.py backtest --type low

# 指定环境
uv run python main.py backtest --env dev
```

### 运行沙盒模式

```bash
# 启动沙盒交易
uv run python main.py sandbox --env sandbox
```

### 运行测试

```bash
# 运行所有测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 运行特定测试
uv run python -m unittest tests.test_adapter -v
```

## 项目结构

```
nautilus-practice/
├── strategy/              # 策略实现
│   ├── common/           # 可复用组件
│   │   ├── indicators/   # 技术指标（Keltner、RS 等）
│   │   ├── signals/      # 信号生成器
│   │   └── universe/     # 标的选择
│   ├── core/             # 策略基类
│   └── *.py              # 具体策略实现
├── backtest/             # 回测引擎
│   ├── engine_high.py    # 高级引擎（推荐）
│   └── engine_low.py     # 低级引擎（调试）
├── sandbox/              # 沙盒交易引擎
├── live/                 # 实盘交易引擎
├── config/               # 配置文件
│   ├── active.yaml       # 活跃配置选择器
│   ├── strategies/       # 策略参数配置
│   └── environments/     # 环境配置（dev/sandbox/live）
├── core/                 # 核心系统
│   ├── adapter.py        # 配置适配器
│   ├── schemas.py        # 配置数据模型
│   └── universe.py       # Universe 生成器
├── scripts/              # 工具脚本
│   ├── generate_universe.py      # 生成 Universe
│   └── analyze_backtest_results.py  # 分析回测结果
├── utils/                # 工具模块
├── data/                 # 数据目录
│   ├── raw/             # 原始 CSV 数据
│   ├── parquet/         # Parquet 缓存
│   └── universe/        # Universe 文件
├── docs/                 # 文档
│   ├── lessons-learned/ # 经验教训
│   └── guides/          # 开发指南
└── tests/                # 测试
```

## 配置系统

### 配置文件结构

```
config/
├── active.yaml                    # 选择活跃的策略和环境
├── strategies/
│   ├── keltner_rs_breakout.yaml  # Keltner RS 突破策略
│   └── dual_thrust.yaml          # Dual Thrust 策略
└── environments/
    ├── dev.yaml                  # 开发/回测环境
    ├── sandbox.yaml              # 沙盒环境
    └── live.yaml                 # 实盘环境
```

### 配置示例

**active.yaml**
```yaml
strategy: keltner_rs_breakout
environment: dev
```

**strategies/keltner_rs_breakout.yaml**
```yaml
name: keltner_rs_breakout
module_path: strategy.keltner_rs_breakout
config_class: KeltnerRSBreakoutConfig
parameters:
  keltner_period: 20
  keltner_multiplier: 2.0
  rs_period: 20
  # ... 其他参数
```

**environments/dev.yaml**
```yaml
backtest:
  start_date: "2022-01-01"
  end_date: "2026-01-01"
  initial_balances:
    USDT: 10000.0

universe:
  enabled: true
  auto_generate: true
  file: "data/universe/universe_15_W-MON.json"
  freq: "W-MON"
  top_n: 15
```

## Universe 动态标的池

Universe 功能自动生成和管理交易标的列表，支持回测和实盘两种模式。

### 特性

- ✅ 基于成交量排名的 Top N 标的筛选
- ✅ 支持周度（W-MON）、双周（2W-MON）、月度（ME）更新频率
- ✅ 回测模式：生成历史所有周期数据
- ✅ 实盘模式：生成当前周期数据
- ✅ 自动过滤非 ASCII 符号

### 生成 Universe

```bash
# 生成回测用 Universe（所有历史周期）
uv run python scripts/generate_universe.py

# 生成实盘用 Universe（当前周期）
uv run python scripts/generate_universe.py --current

# 自定义参数
uv run python scripts/generate_universe.py --top-n 20 --freq ME
```

### 配置 Universe

在环境配置文件中启用 Universe：

```yaml
universe:
  enabled: true              # 启用 Universe
  auto_generate: true        # 自动生成（沙盒/实盘模式）
  file: "data/universe/universe_15_W-MON.json"
  freq: "W-MON"             # 更新频率：W-MON/2W-MON/ME
  top_n: 15                 # Top N 标的
  strict: false             # 严格模式（缺失周期时报错）
```

## 当前策略

### Keltner RS Breakout

基于 Keltner 通道和相对强度的趋势跟踪策略。

**核心逻辑**：
- 使用 Keltner 通道识别趋势突破
- 相对强度（RS）过滤弱势标的
- 动态止损和止盈管理

**关键参数**：
- `keltner_period`: Keltner 通道周期（默认 20）
- `keltner_multiplier`: 通道宽度倍数（默认 2.0）
- `rs_period`: 相对强度周期（默认 20）
- `deviation_threshold`: 偏离阈值（默认 0.30）

### Dual Thrust

经典的日内突破策略。

**核心逻辑**：
- 基于前 N 日高低点计算突破区间
- 日内突破开仓，收盘平仓
- 适合高波动市场

## 核心功能

### 1. 双回测引擎

**高级引擎（推荐）**：
- ✅ 速度提升 32%
- ✅ Parquet 缓存，数据加载速度 10x
- ✅ 完整的统计数据和性能指标
- ✅ 自动生成分析报告

**低级引擎（调试）**：
- ✅ 简单直接，易于调试
- ✅ 适合快速验证策略逻辑
- ⚠️ 统计数据可能不完整

### 2. 模块化策略架构

**可复用组件**：
- `strategy/common/indicators/`: 技术指标（Keltner、RS、ATR 等）
- `strategy/common/signals/`: 信号生成器
- `strategy/common/universe/`: 标的选择逻辑
- `strategy/core/base.py`: 策略基类

**优势**：
- 代码减少 40%
- 复用率提升 700%
- 更易维护和测试

### 3. TUI 终端界面

- 实时进度显示（进度条、百分比）
- 统一日志管理（INFO/DEBUG/WARNING/ERROR）
- 清晰的数据处理总结
- 性能指标实时展示

### 4. 性能分析工具

**13 个性能指标**：
- Sharpe Ratio、Sortino Ratio、Calmar Ratio
- Max Drawdown、Win Rate、Profit Factor
- Total PNL、Total Return、Annualized Return
- 等等

**分析工具**：
```bash
# 分析所有回测结果
python scripts/analyze_backtest_results.py

# 查看最新结果
ls -lht output/backtest/result/*.json | head -3
```

### 5. 过滤器诊断系统

自动诊断零交易问题，提供优化建议。

**功能**：
- 详细的过滤器统计
- 自动零交易警告
- 参数优化建议

**使用方法**：
1. 启用 DEBUG 日志：`level: "DEBUG"`
2. 关闭 components_only：`components_only: false`
3. 查看过滤器统计报告
4. 根据建议调整配置

## 数据管理

### 数据目录结构

```
data/
├── raw/                  # 原始 CSV 数据
│   └── {SYMBOL}/
│       └── binance-{SYMBOL}-{timeframe}-{date_range}.csv
├── parquet/              # Parquet 缓存（高级引擎）
│   └── {SYMBOL}/
│       └── {SYMBOL}_{timeframe}_{date_range}.parquet
└── universe/             # Universe 文件
    └── universe_{top_n}_{freq}.json
```

### 数据格式要求

CSV 文件必须包含以下列：
- `datetime` 或 `timestamp`: 时间列（必需）
- `open`, `high`, `low`, `close`: OHLC 数据
- `volume`: 成交量

### Parquet 缓存

高级引擎自动使用 Parquet 缓存：
- 首次运行生成缓存
- 后续运行速度提升 10x
- 缓存位置：`data/parquet/`

## 常用命令

### 代码检查

```bash
# Lint 检查
uv run ruff check .

# 代码格式化
uv run ruff format .

# 类型检查
uv run pyright
```

### 回测相关

```bash
# 运行回测（高级引擎）
uv run python main.py backtest --type high

# 运行回测（低级引擎）
uv run python main.py backtest --type low

# 指定环境
uv run python main.py backtest --env dev

# 分析回测结果
python scripts/analyze_backtest_results.py

# 查看最新结果
ls -lht output/backtest/result/*.json | head -3
```

### Universe 相关

```bash
# 生成回测用 Universe
uv run python scripts/generate_universe.py

# 生成实盘用 Universe
uv run python scripts/generate_universe.py --current

# 自定义参数
uv run python scripts/generate_universe.py --top-n 20 --freq ME
```

### 测试相关

```bash
# 运行所有测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 运行特定测试文件
uv run python -m unittest tests.test_adapter -v

# 运行特定测试类
uv run python -m unittest tests.test_adapter.TestConfigAdapter -v

# 运行特定测试方法
uv run python -m unittest tests.test_adapter.TestConfigAdapter.test_initialization -v
```

## 常见问题

### Q: 回测产生 0 交易？

**A**: 使用过滤器诊断系统：

1. 启用 DEBUG 日志：`level: "DEBUG"`
2. 关闭 components_only：`components_only: false`
3. 查看过滤器统计报告
4. 根据建议调整配置

**常见原因**：
- `keltner_trigger_multiplier` 过小（建议 2.0-2.3）
- `deviation_threshold` 过小（建议 0.30-0.35）
- 过滤器组合效应导致信号被完全拦截

### Q: 数据加载很慢？

**A**: 使用 Parquet 缓存：

1. 使用高级引擎：`--type high`
2. 首次运行会生成缓存
3. 后续运行速度提升 10x
4. 缓存位置：`data/parquet/`

### Q: 低级引擎回测结果为空？

**A**: 低级引擎可能不会生成完整的统计数据：

1. 优先使用高级引擎：`--type high`
2. 高级引擎提供完整的 PNL 和收益率统计
3. 低级引擎主要用于调试和验证

### Q: 如何分析回测结果？

**A**: 使用分析脚本：

```bash
# 查看所有回测结果排名
python scripts/analyze_backtest_results.py

# 查看最新结果
ls -lht output/backtest/result/*.json | head -3

# 查看特定结果文件
cat output/backtest/result/backtest_result_YYYYMMDD_HHMMSS.json | jq
```

### Q: Universe 文件不存在？

**A**: 生成 Universe 文件：

```bash
# 生成回测用 Universe（所有历史周期）
uv run python scripts/generate_universe.py

# 生成实盘用 Universe（当前周期）
uv run python scripts/generate_universe.py --current
```

### Q: 回测和沙盒可以同时运行吗？

**A**: 可以，使用不同的环境配置：

```bash
# 终端 1：运行回测（使用 dev 环境）
uv run python main.py backtest --env dev

# 终端 2：运行沙盒（使用 sandbox 环境）
uv run python main.py sandbox --env sandbox
```

### Q: 如何添加新策略？

**A**: 参考现有策略实现：

1. 在 `strategy/` 目录创建新策略文件
2. 继承 `BaseStrategy` 或 `TrendFollowingStrategy`
3. 在 `config/strategies/` 创建配置文件
4. 在 `active.yaml` 中激活新策略

详见：`docs/guides/strategy_development.md`

## 文档

### 核心文档

- [架构决策记录](docs/lessons-learned/ARCHITECTURE_DECISIONS.md) - 模块化、性能优化、配置简化
- [TUI 集成经验](docs/lessons-learned/TUI_INTEGRATION.md) - 终端界面实现和生命周期管理
- [Git 工作流](docs/lessons-learned/GIT_WORKFLOW.md) - 分支管理、Commit 规范、CI/CD
- [策略调试与诊断](docs/lessons-learned/STRATEGY_DEBUGGING.md) - 零交易诊断、过滤器优化

### 配置指南

- [Binance API 配置](docs/BINANCE_API_SETUP.md) - Binance API 密钥配置
- [OKX 测试网配置](docs/OKX_TESTNET_SETUP.md) - OKX 测试网配置

### 开发指南

- [策略开发指南](docs/guides/strategy_development.md) - 如何开发新策略
- [AI Agent 开发指南](CLAUDE.md) - 使用 Claude Code 开发的最佳实践

## 注意事项

1. **CSV 数据格式**：时间列必须使用 `datetime` 或 `timestamp`
2. **优先使用高级引擎**：比低级引擎快 32%，且提供完整统计数据
3. **金融计算精度**：使用 `Decimal` 而非 `float`
4. **Python 版本限制**：严格要求 3.12.12+，不支持 3.13
5. **参数调优分支**：策略优化工作应在独立分支进行（如 `feat/strategy-optimization`），避免污染 main 分支
6. **Universe 配置**：回测和实盘使用不同的环境配置，避免冲突

## 开发工作流

### 分支策略

- `main`: 稳定版本，只接受经过测试的 PR
- `feat/*`: 新功能开发
- `fix/*`: Bug 修复
- `docs/*`: 文档更新
- `refactor/*`: 代码重构

### Commit 规范

遵循 Conventional Commits：

```
feat: 添加新功能
fix: 修复 Bug
docs: 文档更新
refactor: 代码重构
test: 测试相关
chore: 构建/工具相关
```

### PR 流程

1. 创建功能分支
2. 开发并测试
3. 提交 PR 到 main
4. CI 检查通过
5. Code Review
6. 合并到 main

## 性能基准

基于 Keltner RS Breakout 策略的回测结果（2022-2026）：

- **回测时间**：~30 秒（高级引擎，Parquet 缓存）
- **数据加载**：~3 秒（Parquet 缓存）
- **策略执行**：~27 秒
- **内存占用**：~500 MB

## 贡献

欢迎贡献！请遵循以下步骤：

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feat/your-feature`
3. 提交更改：`git commit -m 'feat: add your feature'`
4. 推送分支：`git push origin feat/your-feature`
5. 提交 PR

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 联系方式

- GitHub Issues: https://github.com/iridite/nautilus-practice/issues
- 项目主页: https://github.com/iridite/nautilus-practice

---

**注意**：本项目仅用于学习和研究目的，不构成投资建议。量化交易存在风险，请谨慎使用。
