# 新配置系统使用指南

## 📋 概述

新的配置系统使用 **YAML + Pydantic** 架构，提供了更好的可读性、类型安全和维护性。系统完全向后兼容，现有代码无需修改即可使用。

## 🏗️ 配置文件结构

```
config/
├── environments/           # 环境配置
│   ├── base.yaml          # 基础配置
│   ├── dev.yaml           # 开发环境
│   ├── prod.yaml          # 生产环境
│   └── test.yaml          # 测试环境（可选）
├── strategies/            # 策略配置
│   ├── oi_divergence.yaml # OI背离策略
│   ├── rs_squeeze.yaml    # RS挤压策略
│   └── dual_thrust.yaml   # 双推策略
├── active.yaml            # 当前活跃配置
├── schemas.py             # Pydantic数据模型
├── loader.py              # YAML配置加载器
├── manager.py             # 配置管理器
├── migration.py           # 配置迁移工具
└── settings.py            # 向后兼容接口
```

## 🚀 快速开始

### 1. 基本使用（向后兼容）

现有代码无需修改，直接使用：

```python
# 原有的使用方式仍然有效
import config.settings as settings

# 访问配置变量
print(f"交易所: {settings.VENUE}")
print(f"开始日期: {settings.START_DATE}")
print(f"主要交易对: {settings.PRIMARY_SYMBOL}")

# 使用配置函数
config = settings.build_config()
data_cfg = settings.create_data_cfg("BTCUSDT", "1h")
```

### 2. 新配置系统功能

```python
import config.settings as settings

# 查看可用环境和策略
print("可用环境:", settings.get_available_environments())
print("可用策略:", settings.get_available_strategies())

# 切换环境
settings.switch_environment('prod')

# 切换策略
settings.switch_strategy('oi_divergence')

# 验证配置
validation_report = settings.validate_config()
print("配置验证:", validation_report)

# 打印配置摘要
settings.print_config_summary()
```

## 📝 配置文件详解

### 环境配置 (environments/)

#### base.yaml - 基础配置
```yaml
# 交易环境设置
trading:
  venue: "BINANCE"
  instrument_type: "SWAP"
  initial_balance: 100
  currency: "USDT"

# 时间框架设置
timeframes:
  main: "1h"
  trend: "4h"

# 回测设置
backtest:
  start_date: "2025-12-01"
  end_date: "2025-12-30"

# 日志配置
logging:
  level: "INFO"
  file_level: "DEBUG"
  components:
    BacktestEngine: "INFO"
    DataFeed: "INFO"
  components_only: true
```

#### dev.yaml - 开发环境
```yaml
# 继承基础配置
extends: "base.yaml"

# 开发环境特定设置
backtest:
  start_date: "2025-12-01"
  end_date: "2025-12-07"  # 更短的测试周期

logging:
  level: "DEBUG"          # 更详细的日志

trading:
  initial_balance: 50     # 更小的测试资金
```

### 策略配置 (strategies/)

#### oi_divergence.yaml - OI背离策略
```yaml
name: "OIDivergenceStrategy"
module_path: "strategy.oi_divergence_strategy"
config_class: "OIDivergenceStrategyConfig"

parameters:
  # 核心参数
  lookback_bars: 48
  oi_lookback: 12
  oi_decline_threshold: 0.05
  
  # 风险管理
  use_atr_stop: true
  atr_period: 14
  max_position_risk_pct: 0.1
  
  # 仓位控制
  qty_percent: 0.1
  leverage: 1
  max_positions: 1
```

### 活跃配置 (active.yaml)

```yaml
# 当前使用的环境和策略
environment: "dev"
strategy: "rs_squeeze"
primary_symbol: "BTCUSDT"

# 运行时覆盖（可选）
overrides:
  backtest:
    start_date: "2025-12-15"
    end_date: "2025-12-20"
  trading:
    initial_balance: 75
```

## 🔧 高级功能

### 1. 环境变量支持

在配置文件中使用环境变量：

```yaml
trading:
  venue: "BINANCE"
  api_key: "${BINANCE_API_KEY}"           # 必须存在
  api_secret: "${BINANCE_API_SECRET}"
  
database:
  url: "${DATABASE_URL:postgresql://localhost/nautilus}"  # 带默认值
```

### 2. 配置继承

子配置可以继承父配置：

```yaml
# prod.yaml
extends: "base.yaml"

# 只覆盖需要修改的部分
logging:
  level: "WARNING"
  
trading:
  initial_balance: 1000
```

### 3. 配置验证

系统自动验证配置的正确性：

```python
# 验证所有配置文件
report = settings.validate_config()

if report['valid']:
    print("✅ 所有配置都有效")
else:
    print("❌ 配置有问题:")
    for error in report['errors']:
        print(f"  - {error}")
```

### 4. 配置热重载

运行时重新加载配置：

```python
# 重新加载配置
settings.reload_config()

# 或者直接切换
settings.switch_environment('prod')
settings.switch_strategy('oi_divergence')
```

## 🛠️ 配置管理工具

### 1. 配置验证脚本

```bash
# 验证所有配置文件
uv run python -c "
import config.settings as settings
report = settings.validate_config()
print('配置验证结果:', 'PASS' if report['valid'] else 'FAIL')
"
```

### 2. 配置信息查看

```python
# 查看配置系统信息
info = settings.get_config_system_info()
print(f"配置系统版本: {info['version']}")
print(f"配置目录: {info['config_dir']}")
print(f"当前环境: {info['current_environment']}")
print(f"当前策略: {info['current_strategy']}")
```

### 3. 配置迁移

如果需要从旧的settings.py迁移：

```python
from config.migration import migrate_settings

# 执行迁移
report = migrate_settings()
if report['success']:
    print("✅ 迁移成功!")
    print(f"迁移的文件: {report['migrated_files']}")
else:
    print("❌ 迁移失败:", report['errors'])
```

## 📊 配置最佳实践

### 1. 环境分离

- **dev**: 开发环境，使用较短的回测周期和详细日志
- **prod**: 生产环境，使用完整数据和优化的日志级别
- **test**: 测试环境，用于自动化测试

### 2. 策略参数管理

- 将策略参数集中在YAML文件中
- 使用有意义的参数名称和注释
- 为关键参数设置合理的默认值

### 3. 配置版本控制

- 将配置文件纳入版本控制
- 使用分支管理不同环境的配置
- 记录配置变更的原因和影响

### 4. 安全考虑

- 敏感信息使用环境变量
- 不要在配置文件中硬编码API密钥
- 使用`.env`文件管理本地环境变量

## 🔍 故障排除

### 常见问题

1. **配置文件找不到**
   ```
   FileNotFoundError: Config file not found
   ```
   - 检查文件路径是否正确
   - 确保配置目录结构完整

2. **配置验证失败**
   ```
   ConfigValidationError: Invalid configuration
   ```
   - 检查YAML语法是否正确
   - 验证配置项的类型和取值范围

3. **环境变量未找到**
   ```
   Required environment variable 'API_KEY' not found
   ```
   - 设置必需的环境变量
   - 或者为环境变量提供默认值

### 调试技巧

1. **启用详细日志**
   ```yaml
   logging:
     level: "DEBUG"
   ```

2. **验证配置加载**
   ```python
   import config.settings as settings
   settings.print_config_summary()
   ```

3. **检查配置文件语法**
   ```bash
   # 使用Python验证YAML语法
   python -c "import yaml; yaml.safe_load(open('config/active.yaml'))"
   ```

## 🚀 从旧系统迁移

### 迁移步骤

1. **备份现有配置**
   ```bash
   cp config/settings.py config/settings.py.backup
   ```

2. **运行迁移工具**
   ```python
   from config.migration import migrate_settings
   migrate_settings()
   ```

3. **验证迁移结果**
   ```python
   import config.settings as settings
   settings.validate_config()
   ```

4. **测试功能**
   ```bash
   uv run python test_config_system.py
   ```

### 迁移后的优势

- ✅ **可读性**: YAML格式直观易懂
- ✅ **类型安全**: Pydantic提供运行时验证
- ✅ **环境管理**: 轻松切换不同环境配置
- ✅ **向后兼容**: 现有代码无需修改
- ✅ **扩展性**: 新增配置项只需修改YAML文件

## 📚 API参考

### 配置管理器 (ConfigManager)

```python
from config.manager import ConfigManager

manager = ConfigManager()

# 属性访问
manager.VENUE              # 交易所
manager.START_DATE          # 开始日期
manager.END_DATE            # 结束日期
manager.PRIMARY_SYMBOL      # 主要交易对

# 方法调用
manager.build_config()      # 构建回测配置
manager.reload()            # 重新加载配置
manager.switch_environment('prod')  # 切换环境
manager.switch_strategy('oi_divergence')  # 切换策略
```

### 配置加载器 (ConfigLoader)

```python
from config.loader import ConfigLoader

loader = ConfigLoader()

# 加载配置
env_config = loader.load_environment_config('dev')
strategy_config = loader.load_strategy_config('rs_squeeze')
active_config = loader.load_active_config()

# 验证配置
report = loader.validate_config_files()
```

### 向后兼容接口 (settings.py)

```python
import config.settings as settings

# 全局变量（与原系统相同）
settings.VENUE
settings.START_DATE
settings.END_DATE
settings.PRIMARY_SYMBOL
settings.ACTIVE_STRATEGY

# 函数（与原系统相同）
settings.build_config()
settings.create_data_cfg()
settings.create_instrument_cfg()

# 新增功能
settings.switch_environment()
settings.switch_strategy()
settings.validate_config()
settings.print_config_summary()
```

---

## 🎯 总结

新配置系统提供了现代化的配置管理方案，在保持向后兼容的同时，大大提升了配置的可读性、可维护性和扩展性。通过YAML配置文件和Pydantic验证，系统更加健壮和用户友好。

如有问题或需要帮助，请参考本文档或查看配置文件中的注释说明。