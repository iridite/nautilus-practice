# 激进精简配置的安全实施方案

## 🎯 目标

删除冗余配置文件，同时确保所有策略正常运行。

---

## 📋 实施步骤

### 阶段 1：验证当前配置（5 分钟）

#### 1.1 验证所有策略配置可加载
```bash
# 测试配置加载
uv run python -c "
from core.adapter import get_adapter
from pathlib import Path

strategies = ['keltner_rs_breakout', 'dual_thrust', 'funding_arbitrage', 'spot_futures_arbitrage']
for strategy in strategies:
    try:
        # 临时修改 active.yaml
        import yaml
        active_file = Path('config/active.yaml')
        with open(active_file, 'r') as f:
            config = yaml.safe_load(f)
        config['strategy'] = strategy
        config['environment'] = 'dev'
        with open(active_file, 'w') as f:
            yaml.dump(config, f)

        # 加载配置
        adapter = get_adapter()
        adapter.reload()
        print(f'✅ {strategy}: OK')
    except Exception as e:
        print(f'❌ {strategy}: {e}')
"
```

#### 1.2 记录当前配置状态
```bash
# 备份当前配置
cp -r config config.backup.$(date +%Y%m%d_%H%M%S)

# 记录当前 Git 状态
git status > /tmp/config_status_before.txt
```

---

### 阶段 2：安全删除冗余配置（10 分钟）

#### 2.1 检查依赖关系
```bash
# 查找所有引用 funding_arb 或 funding_test 的地方
grep -r "funding_arb\|funding_test" . \
  --include="*.py" \
  --include="*.yaml" \
  --include="*.md" \
  --exclude-dir=".git" \
  --exclude-dir=".venv" \
  --exclude-dir="config.backup.*"
```

**预期结果**：
- 应该只在配置文件本身中找到引用
- 如果在代码中找到引用，需要先修改代码

#### 2.2 删除冗余配置
```bash
# 删除冗余的环境配置
git rm config/environments/funding_arb.yaml
git rm config/environments/funding_test.yaml

# 验证删除
ls config/environments/
```

---

### 阶段 3：优化现有配置（15 分钟）

#### 3.1 优化 base.yaml
```yaml
# config/environments/base.yaml
# 基础环境配置 - 所有环境的共同配置

trading:
  venue: "BINANCE"
  instrument_type: "SWAP"
  currency: "USDT"
  # 移除 initial_balance（让子配置定义）
  # 移除 oms_type（让子配置定义）

# 移除 timeframes（策略不使用）

logging:
  level: "INFO"
  file_level: "DEBUG"
  components:
    BacktestEngine: "INFO"
    DataFeed: "INFO"
    Strategy: "INFO"
  components_only: true

file_cleanup:
  enabled: true
  use_time_rotation: true
  keep_days: 7
  delete_days: 30
  max_files_per_dir: 50
  target_dirs:
    - "log"
    - "output"
```

#### 3.2 优化 dev.yaml
```yaml
# config/environments/dev.yaml
# 开发/回测环境 - 统一的回测环境

extends: base.yaml

backtest:
  start_date: '2024-01-01'
  end_date: '2024-12-31'

logging:
  level: DEBUG
  file_level: DEBUG
  components:
    BacktestEngine: DEBUG
    DataFeed: DEBUG
    Strategy: DEBUG
  components_only: false

trading:
  initial_balance: 100  # 默认小资金测试
  oms_type: NETTING     # 默认净持仓模式

file_cleanup:
  enabled: true
  use_time_rotation: true
  keep_days: 7
  delete_days: 30
  max_files_per_dir: 50
  target_dirs:
    - log
    - output
```

#### 3.3 优化 sandbox.yaml
```yaml
# config/environments/sandbox.yaml
# OKX 测试网环境

extends: base.yaml

# 移除无用的 backtest 字段

sandbox:
  venue: "OKX"
  is_testnet: true

  universe:
    enabled: true
    auto_generate: true
    file: "data/universe/universe_15_W-MON.json"
    freq: "W-MON"
    top_n: 15
    initial_period: null
    strict_mode: false

  allow_missing_instruments: true

  api_key_env: "OKX_API_KEY"
  api_secret_env: "OKX_API_SECRET"
  api_passphrase_env: "OKX_API_PASSPHRASE"

  reconciliation: true
  reconciliation_lookback_mins: 1440
  filter_position_reports: true
  flush_cache_on_start: false

trading:
  venue: "OKX"
  instrument_type: "SWAP"
  initial_balance: 10000
  currency: "USDT"
  oms_type: NETTING

logging:
  level: "INFO"
  file_level: "DEBUG"
  components:
    TradingNode: "INFO"
    LiveExecEngine: "INFO"
    Strategy: "DEBUG"
  components_only: true

file_cleanup:
  enabled: true
  use_time_rotation: true
  keep_days: 14
  delete_days: 60
  max_files_per_dir: 100
  target_dirs:
    - "log"
    - "output"
```

#### 3.4 优化 live.yaml
```yaml
# config/environments/live.yaml
# 实盘环境 - 真实资金交易

extends: base.yaml

live:
  venue: "OKX"
  is_testnet: false

  # 使用 Universe 动态生成标的（移除硬编码的 instrument_ids）
  universe:
    enabled: true
    auto_generate: true
    file: "data/universe/universe_15_W-MON.json"
    freq: "W-MON"
    top_n: 15
    initial_period: null
    strict_mode: false

  allow_missing_instruments: false

  api_key_env: "OKX_MAINNET_API_KEY"
  api_secret_env: "OKX_MAINNET_API_SECRET"
  api_passphrase_env: "OKX_MAINNET_API_PASSPHRASE"

  reconciliation: true
  reconciliation_lookback_mins: 1440
  filter_position_reports: true
  flush_cache_on_start: false

trading:
  venue: "OKX"
  instrument_type: "SWAP"
  initial_balance: 10000
  currency: "USDT"
  oms_type: NETTING

logging:
  level: "INFO"
  file_level: "INFO"
  components:
    TradingNode: "INFO"
    LiveExecEngine: "INFO"
    Strategy: "INFO"
    RiskEngine: "INFO"
    Portfolio: "INFO"
  components_only: true

file_cleanup:
  enabled: true
  use_time_rotation: true
  keep_days: 30
  delete_days: 90
  max_files_per_dir: 200
  target_dirs:
    - "log"
    - "output"
```

---

### 阶段 4：配置 active.yaml 的 overrides（5 分钟）

#### 4.1 为不同策略创建配置示例

**Keltner RS Breakout（默认）**:
```yaml
# config/active.yaml
environment: dev
strategy: keltner_rs_breakout

# 使用默认配置（100 USDT, NETTING）
```

**资金费套利（需要覆盖）**:
```yaml
# config/active.yaml
environment: dev
strategy: funding_arbitrage

overrides:
  trading:
    initial_balance: 10000  # 套利需要更多资金
    oms_type: HEDGING       # 套利需要对冲模式
```

**现货期货套利（需要覆盖）**:
```yaml
# config/active.yaml
environment: dev
strategy: spot_futures_arbitrage

overrides:
  trading:
    initial_balance: 10000
    oms_type: HEDGING
```

---

### 阶段 5：验证所有策略（20 分钟）

#### 5.1 创建验证脚本
```python
# scripts/verify_all_strategies.py
"""验证所有策略配置"""
import yaml
from pathlib import Path
from core.adapter import get_adapter

def verify_strategy(strategy_name: str, overrides: dict = None) -> bool:
    """验证单个策略配置"""
    try:
        # 修改 active.yaml
        active_file = Path('config/active.yaml')
        config = {
            'environment': 'dev',
            'strategy': strategy_name
        }
        if overrides:
            config['overrides'] = overrides

        with open(active_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        # 加载配置
        adapter = get_adapter()
        adapter.reload()

        # 验证关键配置
        strategy_config = adapter.get_strategy_config()
        env_config = adapter.get_environment_config()

        print(f"✅ {strategy_name}")
        print(f"   - Initial balance: {env_config.trading.initial_balance}")
        print(f"   - OMS type: {env_config.trading.oms_type}")
        print(f"   - Venue: {env_config.trading.venue}")

        return True
    except Exception as e:
        print(f"❌ {strategy_name}: {e}")
        return False

def main():
    """验证所有策略"""
    print("=" * 60)
    print("验证所有策略配置")
    print("=" * 60)

    strategies = [
        ('keltner_rs_breakout', None),
        ('dual_thrust', None),
        ('funding_arbitrage', {
            'trading': {
                'initial_balance': 10000,
                'oms_type': 'HEDGING'
            }
        }),
        ('spot_futures_arbitrage', {
            'trading': {
                'initial_balance': 10000,
                'oms_type': 'HEDGING'
            }
        }),
    ]

    results = []
    for strategy, overrides in strategies:
        success = verify_strategy(strategy, overrides)
        results.append((strategy, success))
        print()

    # 总结
    print("=" * 60)
    print("验证结果总结")
    print("=" * 60)
    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"通过: {passed}/{total}")

    if passed == total:
        print("✅ 所有策略配置验证通过！")
        return 0
    else:
        print("❌ 部分策略配置验证失败！")
        return 1

if __name__ == '__main__':
    exit(main())
```

#### 5.2 运行验证
```bash
# 运行验证脚本
uv run python scripts/verify_all_strategies.py

# 预期输出：
# ✅ keltner_rs_breakout
#    - Initial balance: 100
#    - OMS type: NETTING
#    - Venue: BINANCE
#
# ✅ dual_thrust
#    - Initial balance: 100
#    - OMS type: NETTING
#    - Venue: BINANCE
#
# ✅ funding_arbitrage
#    - Initial balance: 10000
#    - OMS type: HEDGING
#    - Venue: BINANCE
#
# ✅ spot_futures_arbitrage
#    - Initial balance: 10000
#    - OMS type: HEDGING
#    - Venue: BINANCE
#
# ✅ 所有策略配置验证通过！
```

---

### 阶段 6：运行实际回测验证（30 分钟）

#### 6.1 快速回测验证（使用小数据集）
```bash
# 1. Keltner RS Breakout
uv run python main.py backtest --type high --env dev

# 2. Funding Arbitrage（需要先配置 overrides）
# 修改 active.yaml 添加 overrides
uv run python main.py backtest --type high --env dev

# 3. Dual Thrust
uv run python main.py backtest --type high --env dev
```

#### 6.2 验证清单
- [ ] 配置加载成功
- [ ] 策略初始化成功
- [ ] 数据加载成功
- [ ] 回测运行成功
- [ ] 结果输出正常

---

### 阶段 7：提交变更（5 分钟）

```bash
# 查看变更
git status
git diff config/

# 提交变更
git add config/
git commit -m "refactor(config): aggressive config simplification

- Remove redundant funding_arb.yaml and funding_test.yaml
- Simplify base.yaml (remove unused timeframes, oms_type, initial_balance)
- Optimize sandbox.yaml (remove unused backtest field)
- Optimize live.yaml (use Universe instead of hardcoded instrument_ids)
- Use active.yaml overrides for strategy-specific configs
- Reduce config files from 10 to 8 (-20%)

BREAKING CHANGE: funding_arb.yaml and funding_test.yaml removed
Use dev.yaml with active.yaml overrides instead
"
```

---

## 🛡️ 安全保障措施

### 1. 备份策略
```bash
# 自动备份
cp -r config config.backup.$(date +%Y%m%d_%H%M%S)

# 如果出问题，快速回滚
cp -r config.backup.YYYYMMDD_HHMMSS/* config/
```

### 2. Git 保护
```bash
# 所有变更都在 Git 中
# 随时可以回滚
git checkout config/
```

### 3. 分步验证
- 每个阶段都有验证步骤
- 发现问题立即停止
- 不要一次性改完所有配置

### 4. 测试覆盖
- 配置加载测试
- 策略初始化测试
- 快速回测验证

---

## ✅ 验证清单

### 配置加载验证
- [ ] base.yaml 可以被正确继承
- [ ] dev.yaml 可以正确加载
- [ ] sandbox.yaml 可以正确加载
- [ ] live.yaml 可以正确加载
- [ ] active.yaml 的 overrides 功能正常

### 策略验证
- [ ] keltner_rs_breakout 配置正确（100 USDT, NETTING）
- [ ] dual_thrust 配置正确（100 USDT, NETTING）
- [ ] funding_arbitrage 配置正确（10000 USDT, HEDGING）
- [ ] spot_futures_arbitrage 配置正确（10000 USDT, HEDGING）

### 回测验证
- [ ] 至少一个策略完整回测成功
- [ ] 回测结果输出正常
- [ ] 日志记录正常

---

## 🚨 回滚方案

如果验证失败：

```bash
# 方案 1：从备份恢复
cp -r config.backup.YYYYMMDD_HHMMSS/* config/

# 方案 2：Git 回滚
git checkout config/

# 方案 3：恢复单个文件
git checkout config/environments/funding_arb.yaml
git checkout config/environments/funding_test.yaml
```

---

## 📊 预期结果

**配置文件数量**:
- 环境配置: 6 → 4 (-33%)
- 策略配置: 4 (不变)
- 总计: 10 → 8 (-20%)

**配置质量**:
- ✅ 无冗余
- ✅ 职责清晰
- ✅ 易于维护
- ✅ 所有策略正常运行

---

## 🎯 总结

这个方案通过**7 个阶段**确保安全：
1. ✅ 验证当前状态
2. ✅ 检查依赖关系
3. ✅ 安全删除冗余配置
4. ✅ 优化现有配置
5. ✅ 配置 overrides
6. ✅ 验证所有策略
7. ✅ 运行实际回测

**预计总时间**: 90 分钟
**风险等级**: 低（有完整的备份和回滚方案）
