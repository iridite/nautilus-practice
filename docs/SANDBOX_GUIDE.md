# Sandbox 模拟盘使用指南

## 概述

Sandbox 模式用于在 OKX 测试网环境中测试策略,使用虚拟资金进行真实的订单执行和市场数据订阅。

## 前置条件

### 1. 获取 OKX 测试网 API 凭证

1. 访问 [OKX 测试网](https://www.okx.com/account/my-api)
2. 创建测试网 API Key
3. 记录以下信息:
   - API Key
   - API Secret
   - API Passphrase

### 2. 配置环境变量

创建 `test.env` 文件（项目根目录）:

```bash
# OKX 测试网 API 凭证
OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_api_secret_here
OKX_API_PASSPHRASE=your_passphrase_here
```

**重要**: `test.env` 已在 `.gitignore` 中,不会被提交到 Git。

## 快速启动

### 方式 1: 使用启动脚本（推荐）

```bash
./scripts/run_sandbox.sh
```

脚本会自动:
- 检查环境变量配置
- 运行预检查
- 启动 Sandbox

### 方式 2: 手动启动

```bash
# 1. 切换到 sandbox 环境
# 编辑 config/active.yaml，设置 environment: "sandbox"

# 2. 运行预检查
uv run python sandbox/preflight.py --env sandbox

# 3. 启动 sandbox
uv run python sandbox/engine.py --env sandbox
```

## 配置说明

### 环境配置: `config/environments/sandbox.yaml`

```yaml
sandbox:
  venue: "OKX"
  is_testnet: true

  # 交易标的列表
  instrument_ids:
    - "ETH-USDT-SWAP.OKX"
    - "SOL-USDT-SWAP.OKX"
    - "BNB-USDT-SWAP.OKX"
    - "DOGE-USDT-SWAP.OKX"
```

### 策略配置: `config/strategies/keltner_rs_breakout.yaml`

关键参数:
- `funding_rate_warning_annual: 50.0` - 现货回退阈值（50% 年化）
- `funding_rate_danger_annual: 100.0` - 熔断器阈值（100% 年化）
- `max_positions: 5` - 最大持仓数量
- `base_risk_pct: 0.05` - 基础风险百分比（5%）

## 资金费率熔断器

策略集成了资金费率熔断器,在入场前自动检查资金费率:

### 决策逻辑

1. **正常执行** (资金费率 < 50% 年化)
   - 使用永续合约正常开仓
   - 日志: `✅ 正常执行`

2. **现货替代** (50% ≤ 资金费率 < 100% 年化)
   - 自动切换到现货标的
   - 避免高额资金费率损耗
   - 日志: `💱 现货替代`

3. **拒绝信号** (资金费率 ≥ 100% 年化)
   - 拒绝开仓信号
   - 避免极端拥挤交易
   - 日志: `🚫 熔断器拒绝信号`

### 监控统计

熔断器会记录统计信息:
- 总信号数
- 拒绝次数
- 现货替代次数
- 正常执行次数

## 常见问题

### 1. API 连接失败

**症状**: `API 健康检查失败`

**解决方案**:
- 检查 `test.env` 文件是否存在且配置正确
- 确认 API Key 有效且未过期
- 检查网络连接
- 确认系统时间同步（时间差 < 5 秒）

### 2. Instrument 文件缺失

**症状**: `Instrument file not found`

**解决方案**:
```bash
# 获取标的信息
uv run python scripts/fetch_instrument.py
```

或在 `sandbox.yaml` 中设置:
```yaml
allow_missing_instruments: true  # 仅用于测试
```

### 3. 熔断器初始化失败

**症状**: `资金费率熔断器初始化失败`

**原因**: 回测模式或无网络环境

**说明**: 这是正常的,熔断器仅在 sandbox/live 模式下工作。回测模式会自动降级。

## 停止 Sandbox

按 `Ctrl+C` 停止运行。系统会:
1. 停止接收新信号
2. 平仓所有持仓（可选）
3. 断开交易所连接
4. 保存日志和状态

## 日志位置

```
log/sandbox/OKX_TESTNET_{timestamp}/
├── runtime/           # 运行时日志
└── ...
```

## 下一步

完成 sandbox 测试后,可以:
1. 分析交易日志和统计数据
2. 调整策略参数
3. 准备实盘部署（谨慎！）

## 安全提示

⚠️ **重要**:
- Sandbox 使用虚拟资金,不会造成真实损失
- 切勿在生产环境使用测试网 API
- 实盘前务必充分测试
- 始终设置合理的风险限制
