# 测试覆盖率提升计划

## 当前状态
- **总覆盖率**: 28.69%
- **已覆盖行数**: 1250 / 4357
- **覆盖率 < 70% 的文件**: 40+ 个

## 优先级分类

### 🔥 高优先级（核心业务逻辑）
需要达到 90%+ 覆盖率：

- [ ] **strategy/core/base.py** (18.9%) - 策略基类，202/249 行未覆盖
- [ ] **strategy/dual_thrust.py** (22.1%) - Dual Thrust 策略，60/77 行未覆盖
- [ ] **strategy/keltner_rs_breakout.py** (18.0%) - Keltner 突破策略，392/478 行未覆盖
- [ ] **core/adapter.py** (68.2%) - 配置适配器，75/236 行未覆盖
- [ ] **core/loader.py** (55.8%) - 数据加载器，57/129 行未覆盖
- [ ] **backtest/engine_low.py** (17.7%) - 回测引擎，204/248 行未覆盖

### ⚡ 中优先级（重要功能）
需要达到 80%+ 覆盖率：

- [ ] **utils/data_management/data_loader.py** (35.1%) - 数据加载，163/251 行未覆盖
- [ ] **utils/data_management/data_manager.py** (32.4%) - 数据管理，46/68 行未覆盖
- [ ] **utils/data_management/data_fetcher.py** (26.9%) - 数据获取，38/52 行未覆盖
- [ ] **utils/data_management/data_retrieval.py** (8.4%) - 数据检索，230/251 行未覆盖
- [ ] **utils/data_management/data_validator.py** (8.0%) - 数据验证，162/176 行未覆盖
- [ ] **utils/symbol_parser.py** (41.9%) - 符号解析，75/129 行未覆盖
- [ ] **utils/time_helpers.py** (40.5%) - 时间工具，25/42 行未覆盖
- [ ] **core/schemas.py** (69.7%) - 配置模式，115/379 行未覆盖

### 💡 低优先级（辅助功能）
需要达到 70%+ 覆盖率：

- [ ] **cli/commands.py** (0.0%) - CLI 命令，62/62 行未覆盖
- [ ] **cli/file_cleanup.py** (0.0%) - 文件清理，105/105 行未覆盖
- [ ] **utils/filename_parser.py** (0.0%) - 文件名解析，30/30 行未覆盖
- [ ] **utils/universe.py** (14.1%) - 交易对管理，73/85 行未覆盖
- [ ] **utils/oi_funding_adapter.py** (13.1%) - OI/Funding 适配器，126/145 行未覆盖

### 🚫 暂不测试（实时交易/脚本）
- **live/engine.py** (0.0%) - 实时交易引擎（需要真实环境）
- **main.py** (0.0%) - 主入口（集成测试覆盖）
- **backtest/engine_high.py** (0.0%) - 高级回测引擎（复杂集成）

## 执行计划

### Week 1: 核心策略模块 (目标: 28% → 40%)
1. **strategy/dual_thrust.py** - 补充策略逻辑测试 (预计 3 小时)
2. **strategy/core/base.py** - 补充基类方法测试 (预计 4 小时)
3. **backtest/engine_low.py** - 补充回测引擎测试 (预计 4 小时)

### Week 2: 数据管理模块 (目标: 40% → 55%)
1. **utils/data_management/data_retrieval.py** - 数据检索测试 (预计 3 小时)
2. **utils/data_management/data_validator.py** - 数据验证测试 (预计 3 小时)
3. **utils/data_management/data_loader.py** - 数据加载测试 (预计 3 小时)
4. **utils/data_management/data_manager.py** - 数据管理测试 (预计 2 小时)

### Week 3: 核心工具模块 (目标: 55% → 65%)
1. **core/loader.py** - 加载器测试 (预计 2 小时)
2. **core/adapter.py** - 适配器测试 (预计 2 小时)
3. **utils/symbol_parser.py** - 符号解析测试 (预计 2 小时)
4. **utils/time_helpers.py** - 时间工具测试 (预计 1 小时)

### Week 4: 辅助功能模块 (目标: 65% → 70%)
1. **utils/filename_parser.py** - 文件名解析测试 (预计 1 小时)
2. **utils/universe.py** - 交易对管理测试 (预计 2 小时)
3. **cli/commands.py** - CLI 命令测试 (预计 2 小时)
4. **core/schemas.py** - 配置模式测试 (预计 2 小时)

## 目标里程碑
- **短期（1 周）**: 28.69% → 40%
- **中期（1 月）**: 40% → 70%
- **长期（3 月）**: 70% → 85%+

## 测试策略
1. **单元测试优先**: 先覆盖独立函数和类方法
2. **边界条件**: 测试异常输入、空值、边界值
3. **集成测试**: 测试模块间交互
4. **Mock 外部依赖**: 使用 pytest-mock 模拟网络请求、文件 I/O

## 成功指标
- 每周覆盖率提升 10-15%
- 核心模块覆盖率 > 90%
- 重���模块覆盖率 > 80%
- 整体覆盖率 > 70%
