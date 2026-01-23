# 配置系统重构设计方案

## 🔍 当前问题分析

当前 `config/settings.py` 存在以下问题：

1. **可读性差**: Python代码混合配置数据，非技术人员难以理解和修改
2. **维护困难**: 配置变更需要修改代码，容易引入语法错误
3. **缺乏验证**: 没有配置项的类型检查和合法性验证
4. **环境管理**: 无法轻松切换不同环境的配置(dev/test/prod)
5. **版本控制**: 配置和代码混在一起，难以独立管理配置版本
6. **扩展性差**: 添加新配置项需要修改多处代码

## 🏗️ 推荐架构方案: YAML + Pydantic

基于行业最佳实践和现有 `config/definitions.py` 的数据结构，推荐使用 **YAML + Pydantic** 的配置系统：

### 🔗 与现有系统的集成

新配置系统将与现有的 `config/definitions.py` 紧密集成：
- 复用现有的 `InstrumentConfig`, `DataConfig`, `StrategyConfig`, `BackTestConfig` 等数据类
- 保持与 NautilusTrader 框架的兼容性
- 利用现有的 `project_root` 路径管理

### 📁 新的配置文件结构

```
config/
├── environments/           # 环境配置
│   ├── base.yaml          # 基础配置
│   ├── dev.yaml           # 开发环境
│   ├── test.yaml          # 测试环境
│   └── prod.yaml          # 生产环境
├── strategies/            # 策略配置
│   ├── oi_divergence.yaml # OI背离策略
│   ├── rs_squeeze.yaml    # RS挤压策略
│   └── dual_thrust.yaml   # 双推策略
├── active.yaml            # 当前活跃配置
├── schemas.py             # Pydantic数据模型
├── loader.py              # YAML配置加载器
├── manager.py             # 配置管理器
└── settings.py            # 向后兼容接口
```

### 📊 配置文件示例

#### config/environments/base.yaml
```yaml
# 基础交易环境配置
trading:
  venue: "BINANCE"
  instrument_type: "SWAP"
  initial_balance: 100
  currency: "USDT"

# 时间框架设置
timeframes:
  main: "1h"
  trend: "4h"

# 回测默认设置
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
    RSSqueezeStrategy: "INFO"
  components_only: true
```

#### config/environments/dev.yaml
```yaml
# 开发环境配置
extends: "base.yaml"

# 覆盖回测时间范围（更短的测试周期）
backtest:
  start_date: "2025-12-01"
  end_date: "2025-12-07"

# 开发环境日志更详细
logging:
  level: "DEBUG"
  file_level: "DEBUG"
```

#### config/strategies/oi_divergence.yaml
```yaml
# OI背离策略配置
name: "OIDivergenceStrategy"
module_path: "strategy.oi_divergence_strategy"
config_class: "OIDivergenceStrategyConfig"

# 策略参数
parameters:
  # 数据设定
  lookback_bars: 48
  oi_lookback: 12
  oi_decline_threshold: 0.05
  funding_rate_threshold_annual: 30.0
  use_funding_filter: true
  breakout_reentry_pct: 0.002
  
  # 出场参数
  tp_use_vwap: true
  vwap_period: 48
  time_stop_bars: 24
  
  # 风险管理 - ATR动态止损
  use_atr_stop: true
  atr_period: 14
  atr_stop_multiplier: 2.0
  stop_loss_pct: 0.01
  
  # 风险管理 - ATR动态仓位
  use_atr_position_sizing: true
  max_position_risk_pct: 0.1
  
  # 滑点控制
  max_slippage_pct: 0.005
  enable_slippage_alert: true
  
  # 仓位控制
  max_positions: 1
  qty_percent: 0.1
  leverage: 1
  
  # 日志控制
  enable_signal_logging: true
  enable_quality_check: true
```

#### config/strategies/rs_squeeze.yaml
```yaml
# RS挤压策略配置
name: "RSSqueezeStrategy"
module_path: "strategy.rs_squeeze"
config_class: "RSSqueezeConfig"

parameters:
  # Universe配置
  universe_filename: "universe_2025_12.json"
  
  # 其他策略参数...
```

#### config/strategies/dual_thrust.yaml
```yaml
# 双推策略配置
name: "DualThrust"
module_path: "strategy.dual_thrust"
config_class: "DualThrustConfig"

parameters:
  lookback_period: 4
  qty_percent: 0.1
```

#### config/active.yaml
```yaml
# 当前活跃配置选择
environment: "dev"
strategy: "rs_squeeze"  # 可选: oi_divergence, rs_squeeze, dual_thrust
primary_symbol: "BTCUSDT"

# 运行时覆盖（可选）
overrides:
  backtest:
    start_date: "2025-12-15"
    end_date: "2025-12-20"
  trading:
    initial_balance: 50
```

### 🔧 核心组件设计

#### config/schemas.py - Pydantic数据模型
```python
from pydantic import BaseModel, Field, validator
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime

class TradingConfig(BaseModel):
    venue: str = "BINANCE"
    instrument_type: str = "SWAP"
    initial_balance: Decimal = Decimal("100")
    currency: str = "USDT"

class TimeframesConfig(BaseModel):
    main: str = "1h"
    trend: str = "4h"
    
    @validator('main', 'trend')
    def validate_timeframe(cls, v):
        # 验证时间框架格式
        if not v.endswith(('m', 'h', 'd')):
            raise ValueError('Timeframe must end with m, h, or d')
        return v

class BacktestConfig(BaseModel):
    start_date: str
    end_date: str
    
    @validator('start_date', 'end_date')
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')
        return v

class LoggingConfig(BaseModel):
    level: str = "INFO"
    file_level: str = "DEBUG"
    components: Dict[str, str] = {}
    components_only: bool = True

class StrategyConfig(BaseModel):
    name: str
    module_path: str
    config_class: Optional[str] = None
    parameters: Dict[str, Any] = {}

class EnvironmentConfig(BaseModel):
    trading: TradingConfig = TradingConfig()
    timeframes: TimeframesConfig = TimeframesConfig()
    backtest: BacktestConfig
    logging: LoggingConfig = LoggingConfig()

class ActiveConfig(BaseModel):
    environment: str = "dev"
    strategy: str
    primary_symbol: str = "BTCUSDT"
    overrides: Optional[Dict[str, Any]] = None
```

#### config/loader.py - YAML配置加载器
```python
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from .schemas import EnvironmentConfig, StrategyConfig, ActiveConfig

class ConfigLoader:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.environments_dir = config_dir / "environments"
        self.strategies_dir = config_dir / "strategies"
    
    def load_environment_config(self, env_name: str) -> EnvironmentConfig:
        """加载环境配置，支持继承"""
        env_file = self.environments_dir / f"{env_name}.yaml"
        config_data = self._load_yaml_with_inheritance(env_file)
        return EnvironmentConfig(**config_data)
    
    def load_strategy_config(self, strategy_name: str) -> StrategyConfig:
        """加载策略配置"""
        strategy_file = self.strategies_dir / f"{strategy_name}.yaml"
        config_data = self._load_yaml(strategy_file)
        return StrategyConfig(**config_data)
    
    def load_active_config(self) -> ActiveConfig:
        """加载当前活跃配置"""
        active_file = self.config_dir / "active.yaml"
        config_data = self._load_yaml(active_file)
        return ActiveConfig(**config_data)
    
    def _load_yaml_with_inheritance(self, file_path: Path) -> Dict[str, Any]:
        """加载YAML文件，支持extends继承"""
        config_data = self._load_yaml(file_path)
        
        if 'extends' in config_data:
            parent_file = self.environments_dir / config_data['extends']
            parent_data = self._load_yaml_with_inheritance(parent_file)
            # 深度合并配置
            merged_data = self._deep_merge(parent_data, config_data)
            del merged_data['extends']  # 移除extends字段
            return merged_data
        
        return config_data
    
    def _load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """加载单个YAML文件"""
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """深度合并两个字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
```

#### config/manager.py - 配置管理器
```python
from pathlib import Path
from typing import Optional
from .loader import ConfigLoader
from .schemas import EnvironmentConfig, StrategyConfig, ActiveConfig
from ..definitions import BackTestConfig, InstrumentConfig, DataConfig, StrategyConfig as LegacyStrategyConfig

class ConfigManager:
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(__file__).parent
        
        self.loader = ConfigLoader(config_dir)
        self.active_config = self.loader.load_active_config()
        self.env_config = self.loader.load_environment_config(self.active_config.environment)
        self.strategy_config = self.loader.load_strategy_config(self.active_config.strategy)
    
    def get_backtest_config(self) -> BackTestConfig:
        """构建回测配置，替换settings.build_config()"""
        # 这里实现原settings.py中build_config()的逻辑
        # 但使用新的配置数据源
        pass
    
    def get_strategy_config(self) -> LegacyStrategyConfig:
        """获取策略配置，兼容现有格式"""
        pass
    
    def get_primary_symbol(self) -> str:
        """获取主要交易对"""
        return self.active_config.primary_symbol
    
    def get_venue(self) -> str:
        """获取交易所"""
        return self.env_config.trading.venue
    
    def reload(self):
        """热重载配置"""
        self.active_config = self.loader.load_active_config()
        self.env_config = self.loader.load_environment_config(self.active_config.environment)
        self.strategy_config = self.loader.load_strategy_config(self.active_config.strategy)
```

### 🔄 迁移策略

#### 阶段1: 实现新配置系统
- 创建新的配置文件结构和Python模块
- 保持现有 `settings.py` 接口不变
- 新系统与旧系统并行运行

#### 阶段2: 配置迁移工具
```python
# config/migration.py
class ConfigMigrator:
    def migrate_from_settings(self):
        """将现有settings.py配置转换为YAML格式"""
        pass
```

#### 阶段3: 渐进式替换
- 更新 `settings.py` 内部实现使用新配置系统
- 保持对外API不变
- 逐步更新调用方使用新API

#### 阶段4: 完全迁移
- 移除旧的实现代码
- 更新文档和示例

### 💡 关键优势

1. **可读性**: YAML格式直观易懂，非程序员也能修改
2. **类型安全**: Pydantic提供运行时验证和IDE智能提示
3. **环境管理**: 轻松切换dev/test/prod配置
4. **版本控制**: 配置变更历史清晰可追踪
5. **扩展性**: 新增配置项只需修改YAML和schema
6. **热重载**: 支持运行时配置更新
7. **向后兼容**: 现有代码无需大规模修改

### 🚀 实施建议

1. **优先级**: 先实现核心功能，再添加高级特性
2. **测试**: 确保新系统与现有功能完全兼容
3. **文档**: 提供详细的配置指南和迁移文档
4. **渐进式**: 分阶段实施，降低风险

## 🔧 高级特性和考虑因素

### 1. 配置验证和约束

#### 业务规则验证
```python
# config/validators.py
from pydantic import validator, root_validator
from datetime import datetime

class BacktestConfigValidator(BaseModel):
    @validator('start_date', 'end_date')
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')
        return v
    
    @root_validator
    def validate_date_range(cls, values):
        start = values.get('start_date')
        end = values.get('end_date')
        if start and end:
            start_dt = datetime.strptime(start, '%Y-%m-%d')
            end_dt = datetime.strptime(end, '%Y-%m-%d')
            if start_dt >= end_dt:
                raise ValueError('start_date must be before end_date')
            
            # OI数据限制：Binance仅提供最近30天数据
            if (end_dt - start_dt).days > 30:
                raise ValueError('Binance OI data limited to 30 days range')
        return values

class StrategyParameterValidator(BaseModel):
    @validator('leverage')
    def validate_leverage(cls, v):
        if not 1 <= v <= 100:
            raise ValueError('Leverage must be between 1 and 100')
        return v
    
    @validator('qty_percent')
    def validate_position_size(cls, v):
        if not 0 < v <= 1:
            raise ValueError('Position size must be between 0 and 1')
        return v
```

#### 交易所特定验证
```python
class VenueSpecificValidator:
    @staticmethod
    def validate_binance_constraints(config: dict):
        """验证Binance特定约束"""
        if config.get('venue') == 'BINANCE':
            # 验证OI数据时间范围
            # 验证支持的交易对
            # 验证费率设置
            pass
    
    @staticmethod
    def validate_okx_constraints(config: dict):
        """验证OKX特定约束"""
        pass
```

### 2. 配置安全和敏感信息管理

#### 环境变量集成
```yaml
# config/environments/prod.yaml
trading:
  venue: "BINANCE"
  api_key: "${BINANCE_API_KEY}"  # 从环境变量读取
  api_secret: "${BINANCE_API_SECRET}"
  
# 支持默认值
database:
  url: "${DATABASE_URL:postgresql://localhost/nautilus}"
```

#### 配置加密
```python
# config/encryption.py
from cryptography.fernet import Fernet
import os

class ConfigEncryption:
    def __init__(self):
        self.key = os.environ.get('CONFIG_ENCRYPTION_KEY')
        if self.key:
            self.cipher = Fernet(self.key.encode())
    
    def encrypt_sensitive_fields(self, config: dict) -> dict:
        """加密敏感配置字段"""
        sensitive_fields = ['api_key', 'api_secret', 'password']
        # 实现加密逻辑
        return config
    
    def decrypt_sensitive_fields(self, config: dict) -> dict:
        """解密敏感配置字段"""
        # 实现解密逻辑
        return config
```

### 3. 配置性能优化

#### 配置缓存
```python
# config/cache.py
from functools import lru_cache
from typing import Dict, Any
import hashlib
import json

class ConfigCache:
    def __init__(self):
        self._cache = {}
        self._file_hashes = {}
    
    def get_cached_config(self, config_path: str) -> Optional[Dict[Any, Any]]:
        """获取缓存的配置，如果文件未变更"""
        current_hash = self._get_file_hash(config_path)
        if config_path in self._cache and self._file_hashes.get(config_path) == current_hash:
            return self._cache[config_path]
        return None
    
    def cache_config(self, config_path: str, config: Dict[Any, Any]):
        """缓存配置和文件哈希"""
        self._cache[config_path] = config
        self._file_hashes[config_path] = self._get_file_hash(config_path)
    
    def _get_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
```

#### 懒加载配置
```python
class LazyConfigManager:
    def __init__(self):
        self._configs = {}
        self._loaded = set()
    
    @property
    def strategy_config(self):
        if 'strategy' not in self._loaded:
            self._configs['strategy'] = self._load_strategy_config()
            self._loaded.add('strategy')
        return self._configs['strategy']
```

### 4. 配置监控和热重载

#### 文件监控
```python
# config/watcher.py
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading

class ConfigWatcher(FileSystemEventHandler):
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.observer = Observer()
    
    def on_modified(self, event):
        if event.src_path.endswith('.yaml'):
            print(f"Config file changed: {event.src_path}")
            self.config_manager.reload()
    
    def start_watching(self, config_dir: str):
        self.observer.schedule(self, config_dir, recursive=True)
        self.observer.start()
```

#### 配置变更通知
```python
from typing import Callable, List

class ConfigChangeNotifier:
    def __init__(self):
        self._callbacks: List[Callable] = []
    
    def register_callback(self, callback: Callable):
        """注册配置变更回调"""
        self._callbacks.append(callback)
    
    def notify_change(self, config_path: str, old_config: dict, new_config: dict):
        """通知配置变更"""
        for callback in self._callbacks:
            try:
                callback(config_path, old_config, new_config)
            except Exception as e:
                print(f"Config change callback error: {e}")
```

### 5. 配置版本管理和回滚

#### 配置版本控制
```python
# config/versioning.py
import json
from datetime import datetime
from pathlib import Path

class ConfigVersionManager:
    def __init__(self, versions_dir: Path):
        self.versions_dir = versions_dir
        self.versions_dir.mkdir(exist_ok=True)
    
    def save_version(self, config_name: str, config: dict) -> str:
        """保存配置版本"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        version_id = f"{config_name}_{timestamp}"
        version_file = self.versions_dir / f"{version_id}.json"
        
        with open(version_file, 'w') as f:
            json.dump({
                'version_id': version_id,
                'timestamp': timestamp,
                'config': config
            }, f, indent=2)
        
        return version_id
    
    def rollback_to_version(self, version_id: str) -> dict:
        """回滚到指定版本"""
        version_file = self.versions_dir / f"{version_id}.json"
        if not version_file.exists():
            raise ValueError(f"Version {version_id} not found")
        
        with open(version_file, 'r') as f:
            version_data = json.load(f)
        
        return version_data['config']
```

### 6. 配置模板和生成器

#### 配置模板系统
```python
# config/templates.py
from jinja2 import Template
from typing import Dict, Any

class ConfigTemplateEngine:
    def __init__(self):
        self.templates = {
            'strategy': self._load_strategy_template(),
            'environment': self._load_environment_template()
        }
    
    def generate_strategy_config(self, strategy_name: str, params: Dict[str, Any]) -> str:
        """根据模板生成策略配置"""
        template = self.templates['strategy']
        return template.render(strategy_name=strategy_name, **params)
    
    def _load_strategy_template(self) -> Template:
        template_str = """
# {{ strategy_name }} 策略配置
name: "{{ strategy_name }}"
module_path: "strategy.{{ strategy_name.lower() }}"

parameters:
{% for key, value in params.items() %}
  {{ key }}: {{ value }}
{% endfor %}
"""
        return Template(template_str)
```

### 7. 配置文档自动生成

#### Schema文档生成
```python
# config/docs_generator.py
from pydantic import BaseModel
from typing import Dict, Any

class ConfigDocsGenerator:
    def generate_schema_docs(self, model: BaseModel) -> str:
        """从Pydantic模型生成配置文档"""
        schema = model.schema()
        return self._render_schema_markdown(schema)
    
    def _render_schema_markdown(self, schema: Dict[str, Any]) -> str:
        """渲染Schema为Markdown文档"""
        # 实现Markdown文档生成逻辑
        pass
```

### 8. 配置测试框架

#### 配置单元测试
```python
# tests/test_config_system.py
import pytest
from config.manager import ConfigManager
from config.schemas import EnvironmentConfig

class TestConfigSystem:
    def test_config_validation(self):
        """测试配置验证"""
        # 测试有效配置
        valid_config = {
            'trading': {'venue': 'BINANCE'},
            'backtest': {'start_date': '2025-12-01', 'end_date': '2025-12-30'}
        }
        config = EnvironmentConfig(**valid_config)
        assert config.trading.venue == 'BINANCE'
        
        # 测试无效配置
        with pytest.raises(ValueError):
            invalid_config = {
                'backtest': {'start_date': '2025-12-30', 'end_date': '2025-12-01'}
            }
            EnvironmentConfig(**invalid_config)
    
    def test_config_inheritance(self):
        """测试配置继承"""
        pass
    
    def test_config_hot_reload(self):
        """测试配置热重载"""
        pass
```

### 9. 配置迁移和兼容性

#### 配置版本迁移
```python
# config/migration.py
from typing import Dict, Any, List
from abc import ABC, abstractmethod

class ConfigMigration(ABC):
    @abstractmethod
    def migrate(self, old_config: Dict[str, Any]) -> Dict[str, Any]:
        pass

class V1ToV2Migration(ConfigMigration):
    """从v1配置格式迁移到v2"""
    def migrate(self, old_config: Dict[str, Any]) -> Dict[str, Any]:
        # 实现具体的迁移逻辑
        new_config = old_config.copy()
        # 重命名字段、调整结构等
        return new_config

class ConfigMigrator:
    def __init__(self):
        self.migrations: List[ConfigMigration] = [
            V1ToV2Migration(),
            # 添加更多迁移
        ]
    
    def migrate_config(self, config: Dict[str, Any], from_version: str, to_version: str) -> Dict[str, Any]:
        """执行配置迁移"""
        # 实现版本间的迁移逻辑
        pass
```

### 10. 配置最佳实践指南

#### 配置命名约定
- **环境配置**: `base.yaml`, `dev.yaml`, `test.yaml`, `prod.yaml`
- **策略配置**: `{strategy_name}.yaml` (小写，下划线分隔)
- **配置字段**: 使用snake_case命名
- **布尔值**: 使用`true`/`false`而非`yes`/`no`

#### 配置组织原则
1. **单一职责**: 每个配置文件专注于特定领域
2. **最小化重复**: 通过继承减少配置重复
3. **环境隔离**: 不同环境的配置完全分离
4. **敏感信息**: 使用环境变量或加密存储
5. **文档化**: 为每个配置项提供注释说明

#### 配置部署策略
```yaml
# 生产环境配置部署检查清单
deployment:
  pre_checks:
    - validate_all_configs
    - check_environment_variables
    - verify_file_permissions
    - test_config_loading
  
  post_checks:
    - verify_strategy_initialization
    - check_data_connectivity
    - validate_risk_parameters
```

这个架构既解决了当前问题，又为未来的功能扩展提供了坚实基础。通过这些高级特性，配置系统将具备企业级的可靠性、安全性和可维护性。