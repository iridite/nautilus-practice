# 配置文件深度分析与优化建议

## 📊 当前配置文件清单（6 个环境配置）

### 1. base.yaml - 基础配置模板
**用途**: 所有环境配置的基础模板
**内容**:
- 交易所: BINANCE
- OMS 类型: HEDGING
- 初始资金: 100,000 USDT
- 时间框架: main=1h, trend=4h
- 日志配置
- 文件清理配置

**问题分析**:
- ❌ `timeframes` 字段无用（策略不使用）
- ❌ `oms_type: HEDGING` 对大多数策略不适用（只有套利策略需要）
- ⚠️ `initial_balance: 100000` 太大（dev 环境会覆盖为 100）

**优化建议**:
```yaml
# 简化后的 base.yaml
trading:
  venue: "BINANCE"
  instrument_type: "SWAP"
  currency: "USDT"
  # 移除 initial_balance（让子配置自己定义）
  # 移除 oms_type（让子配置自己定义）

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

---

### 2. dev.yaml - 开发/回测环境
**用途**: 本地策略回测和开发测试
**内容**:
- 回测时间: 2024-01-01 ~ 2024-12-31
- 初始资金: 100 USDT
- 日志级别: DEBUG

**问题分析**:
- ✅ 设计合理
- ✅ 灵活性高（可以修改日期范围）
- ✅ 小资金测试（100 USDT）

**优化建议**:
- 保持现状，无需修改

---

### 3. sandbox.yaml - OKX 测试网
**用途**: OKX 测试网模拟实盘交易
**内容**:
- 交易所: OKX
- Universe 配置
- API 环境变量
- 初始资金: 10,000 USDT

**问题分析**:
- ✅ 设计合理
- ✅ 测试网专用配置
- ⚠️ `backtest` 字段无用（sandbox 不做回测）

**优化建议**:
```yaml
# 移除无用的 backtest 配置
# backtest:
#   start_date: "2022-01-01"
#   end_date: "2026-01-01"
```

---

### 4. live.yaml - 实盘环境
**用途**: 真实资金交易
**内容**:
- 交易所: OKX
- 硬编码的 instrument_ids
- API 环境变量（主网）
- 初始资金: 10,000 USDT

**问题分析**:
- ⚠️ 硬编码的 `instrument_ids`（应该使用 Universe）
- ⚠️ 没有 `backtest` 字段（但 schema 可能要求）

**优化建议**:
```yaml
# 移除硬编码的 instrument_ids
# 使用 Universe 动态生成
live:
  venue: "OKX"
  is_testnet: false

  # Universe 配置（与 sandbox 一致）
  universe:
    enabled: true
    auto_generate: true
    file: "data/universe/universe_15_W-MON.json"
    freq: "W-MON"
    top_n: 15
```

---

### 5. funding_arb.yaml - 资金费套利回测
**用途**: 资金费套利策略专用回测环境
**内容**:
- 回测时间: 2024-01-01 ~ 2024-12-31
- 初始资金: 10,000 USDT
- 策略配置: FundingArbitrageStrategy

**问题分析**:
- ❌ `strategy` 字段无用（应该在 active.yaml 中指定）
- ⚠️ 与 `dev.yaml` 高度重复（只有初始资金不同）

**优化建议**:
- **删除此文件**，使用 `dev.yaml` + 修改 `initial_balance`

---

### 6. funding_test.yaml - 资金费套利测试
**用途**: 资金费套利策略测试环境
**内容**:
- 回测时间: 2024-01-01 ~ 2024-12-31
- 初始资金: 100,000 USDT
- 日志级别: INFO

**问题分析**:
- ❌ 与 `funding_arb.yaml` 高度重复（只有初始资金和日志级别不同）
- ❌ 与 `dev.yaml` 高度重复

**优化建议**:
- **删除此文件**，使用 `dev.yaml` + 修改 `initial_balance`

---

## 🎯 优化方案

### 方案 A：激进精简（推荐）

**保留 3 个环境配置**:
1. ✅ `base.yaml` - 基础模板（简化）
2. ✅ `dev.yaml` - 统一的开发/回测环境
3. ✅ `sandbox.yaml` - OKX 测试网
4. ✅ `live.yaml` - 实盘环境（优化）

**删除 2 个环境配置**:
- ❌ `funding_arb.yaml` - 冗余（用 dev.yaml 替代）
- ❌ `funding_test.yaml` - 冗余（用 dev.yaml 替代）

**配置差异化方案**:
```yaml
# 需要不同初始资金时，在 active.yaml 中覆盖
environment: dev
strategy: funding_arbitrage

overrides:
  trading:
    initial_balance: 10000  # 覆盖 dev.yaml 的 100
```

**优势**:
- 🎯 配置文件从 6 个减少到 4 个（-33%）
- 🔧 更易维护
- 🚀 避免配置重复

---

### 方案 B：保守优化

**保留所有 6 个环境配置**，但优化内容:

1. **base.yaml**:
   - 移除 `timeframes`
   - 移除 `oms_type`（让子配置定义）
   - 移除 `initial_balance`（让子配置定义）

2. **sandbox.yaml**:
   - 移除无用的 `backtest` 字段

3. **live.yaml**:
   - 移除硬编码的 `instrument_ids`
   - 使用 Universe 配置

4. **funding_arb.yaml**:
   - 移除 `strategy` 字段

5. **funding_test.yaml**:
   - 移除冗余配置

---

## 📊 对比分析

| 配置文件 | 用途 | 是否必需 | 可替代方案 |
|---------|------|---------|-----------|
| `base.yaml` | 基础模板 | ✅ 必需 | - |
| `dev.yaml` | 开发/回测 | ✅ 必需 | - |
| `sandbox.yaml` | OKX 测试网 | ✅ 必需 | - |
| `live.yaml` | 实盘环境 | ✅ 必需 | - |
| `funding_arb.yaml` | 套利回测 | ❌ 冗余 | `dev.yaml` + `overrides` |
| `funding_test.yaml` | 套利测试 | ❌ 冗余 | `dev.yaml` + `overrides` |

---

## 🔍 深层问题分析

### 问题 1: 配置职责混乱

**现状**:
- `funding_arb.yaml` 中有 `strategy` 字段
- 环境配置不应该指定策略

**解决方案**:
- 策略选择应该在 `active.yaml` 中
- 环境配置只负责环境相关设置

---

### 问题 2: 配置重复

**现状**:
- `dev.yaml`, `funding_arb.yaml`, `funding_test.yaml` 高度重复
- 只有 `initial_balance` 和日志级别不同

**解决方案**:
- 使用单一 `dev.yaml`
- 通过 `active.yaml` 的 `overrides` 覆盖差异

---

### 问题 3: 无用字段

**现状**:
- `base.yaml` 的 `timeframes` 字段无人使用
- `sandbox.yaml` 的 `backtest` 字段无用
- `live.yaml` 硬编码 `instrument_ids`

**解决方案**:
- 删除无用字段
- 使用 Universe 动态生成标的

---

## 💡 最终推荐

### 推荐方案：激进精简

**删除**:
- ❌ `funding_arb.yaml`
- ❌ `funding_test.yaml`

**优化**:
- 🔧 简化 `base.yaml`（移除无用字段）
- 🔧 优化 `sandbox.yaml`（移除 backtest）
- 🔧 优化 `live.yaml`（使用 Universe）

**使用方式**:
```yaml
# active.yaml - 资金费套利回测
environment: dev
strategy: funding_arbitrage
overrides:
  trading:
    initial_balance: 10000
    oms_type: HEDGING  # 套利策略需要

# active.yaml - Keltner RS 回测
environment: dev
strategy: keltner_rs_breakout
overrides:
  trading:
    initial_balance: 100
    oms_type: NETTING  # 单向策略
```

**最终配置文件数量**:
- 环境配置: 6 → **4** (-33%)
- 策略配置: 4 (不变)
- **总计**: 10 → **8** (-20%)

---

## ✅ 优化清单

- [ ] 删除 `funding_arb.yaml`
- [ ] 删除 `funding_test.yaml`
- [ ] 简化 `base.yaml`（移除 timeframes, oms_type, initial_balance）
- [ ] 优化 `sandbox.yaml`（移除 backtest）
- [ ] 优化 `live.yaml`（使用 Universe）
- [ ] 更新文档

---

## 🎉 预期成果

**配置文件数量**:
- 从 10 个减少到 **8 个**（-20%）
- 环境配置从 6 个减少到 **4 个**（-33%）

**配置质量**:
- ✅ 职责更清晰
- ✅ 重复更少
- ✅ 更易维护
- ✅ 更灵活
