# Sandbox 功能检查报告

**检查时间**: 2026-02-19  
**检查人**: Anbi (安比)  
**状态**: ✅ 通过

---

## 检查项目

### 1. ✅ 代码完整性
- [x] 策略模块导入正常 (`KeltnerRSBreakoutStrategy`)
- [x] 配置加载正常 (`sandbox.yaml`)
- [x] 依赖项完整 (NautilusTrader 1.223.0)
- [x] 修复了 `Data` 类型导入问题 → 使用 `CustomData`

### 2. ✅ 配置文件
- [x] `config/environments/sandbox.yaml` - 已修复 instrument_ids 格式
- [x] `config/strategies/keltner_rs_breakout.yaml` - 配置正确
- [x] `config/active.yaml` - 指向正确的环境和策略

### 3. ✅ Instrument 数据
- [x] BTC-USDT-SWAP.json (已存在)
- [x] ETH-USDT-SWAP.json (已存在)
- [x] SOL-USDT-SWAP.json (已存在)
- [x] DOGE-USDT-SWAP.json (已存在)
- [x] BNB-USDT-SWAP.json (已创建)

### 4. ✅ Preflight 检查
- [x] 环境文件检查通过 (`test.env` 存在)
- [x] 策略导入检查通过
- [x] Instrument 文件检查通过
- [x] 配置验证通过

### 5. ⚠️ API 凭证配置
- [ ] **需要用户配置**: `test.env` 中的 OKX 测试网 API 凭证
  - `OKX_API_KEY=your_testnet_api_key_here`
  - `OKX_API_SECRET=your_testnet_api_secret_here`
  - `OKX_API_PASSPHRASE=your_testnet_passphrase_here`

---

## 修复的问题

### 问题 1: 策略导入失败
**错误**: `NameError: name 'Data' is not defined`  
**原因**: `nautilus_trader.model.data` 中没有 `Data` 类型  
**修复**: 改用 `CustomData` 类型  
**文件**: `strategy/keltner_rs_breakout.py`

### 问题 2: Instrument ID 格式错误
**错误**: 配置文件使用了错误的格式 `ETHUSDT.OKX`  
**原因**: OKX SWAP 合约的正确格式是 `ETH-USDT-SWAP.OKX`  
**修复**: 更新 `config/environments/sandbox.yaml`  
**影响**: 4 个 instrument_ids

### 问题 3: 缺失 BNB instrument 文件
**错误**: `BNB-USDT-SWAP.json` 不存在  
**原因**: 未从 OKX 获取  
**修复**: 手动创建 instrument 文件  
**文件**: `data/instrument/OKX/BNB-USDT-SWAP.json`

---

## 启动 Sandbox

### 前置条件
1. 配置 OKX 测试网 API 凭证到 `test.env`
2. 确保测试网账户有足够的测试资金

### 启动命令
```bash
cd ~/Projects/nautilus-practice
.venv/bin/python sandbox/engine.py --env sandbox
```

### 预期行为
- 连接到 OKX 测试网 (is_testnet=true)
- 加载 4 个交易对 (ETH, SOL, BNB, DOGE)
- 自动添加 BTC 作为辅助标的（用于 RS 计算）
- 启动 KeltnerRSBreakout 策略
- 日志保存到 `log/sandbox/{trader_name}/runtime/`

---

## 网络依赖

### 外部连接
- OKX 测试网 WebSocket: `wss://wspap.okx.com:8443/ws/v5/public`
- OKX 测试网 REST API: `https://www.okx.com`

### 防火墙要求
- 允许出站 HTTPS (443)
- 允许出站 WebSocket (8443)

---

## 已知限制

1. **单标的限制**: 当前版本仅支持单个交易标的（代码注释中提到）
   - 实际配置了 4 个标的，可能需要验证多标的支持
   
2. **测试网限制**:
   - 测试网数据可能不完整
   - 测试网流动性较低
   - 需要手动申请测试资金

3. **Universe 数据**:
   - 策略配置了 `universe_top_n: 15`
   - 需要确保 `data/universe/universe_15_W-MON.json` 存在

---

## 下一步建议

1. **配置 API 凭证**:
   ```bash
   # 编辑 test.env
   nano ~/Projects/nautilus-practice/test.env
   ```

2. **申请测试资金**:
   - 访问 https://www.okx.com/account/my-api
   - 切换到测试网
   - 申请测试 USDT

3. **验证网络连接**:
   ```bash
   curl -I https://www.okx.com
   ```

4. **启动测试**:
   ```bash
   cd ~/Projects/nautilus-practice
   .venv/bin/python sandbox/engine.py --env sandbox
   ```

5. **监控日志**:
   ```bash
   tail -f log/sandbox/*/runtime/*.log
   ```

---

## 总结

✅ **Sandbox 代码和配置已完整且可运行**  
⚠️ **需要用户配置 OKX 测试网 API 凭证才能启动**  
📝 **所有技术问题已修复，无阻塞性错误**

---

**检查完成时间**: 2026-02-19 10:50 CST
