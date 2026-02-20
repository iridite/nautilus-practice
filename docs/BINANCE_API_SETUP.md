# Binance API 配置指南

本文档介绍如何配置 Binance API 以在 Nautilus Practice 项目中使用。

## 目录

- [API 申请](#api-申请)
- [环境配置](#环境配置)
- [Testnet 配置](#testnet-配置)
- [安全建议](#安全建议)
- [常见问题](#常见问题)

---

## API 申请

### 主网 API

1. **登录 Binance 账户**
   - 访问 [Binance](https://www.binance.com)
   - 登录你的账户

2. **创建 API Key**
   - 进入 [API 管理页面](https://www.binance.com/en/my/settings/api-management)
   - 点击 "Create API"
   - 选择 "System generated" (系统生成)
   - 输入 API 标签名称（如 "Nautilus Trading Bot"）
   - 完成安全验证（2FA、邮箱验证等）

3. **配置 API 权限**
   - ✅ **Enable Reading** (必需)
   - ✅ **Enable Spot & Margin Trading** (如果交易现货)
   - ✅ **Enable Futures** (如果交易合约)
   - ❌ **Enable Withdrawals** (不建议开启)

4. **IP 白名单设置**（强烈推荐）
   - 在 API 设置中添加你的服务器 IP
   - 限制 API 只能从特定 IP 访问
   - 提高账户安全性

5. **保存凭证**
   - **API Key**: 公开密钥，可以分享
   - **Secret Key**: 私密密钥，**绝对不能泄露**
   - Secret Key 只显示一次，请妥善保存

### Testnet API

1. **注册 Testnet 账户**
   - 访问 [Binance Futures Testnet](https://testnet.binancefuture.com)
   - 使用 GitHub 或 Google 账号登录
   - 无需 KYC，免费获得测试资金

2. **创建 Testnet API Key**
   - 登录后进入 API 管理页面
   - 点击 "Generate HMAC_SHA256 Key"
   - 保存 API Key 和 Secret Key

3. **获取测试资金**
   - Testnet 账户会自动获得虚拟 USDT
   - 可以在 Testnet 界面申请更多测试资金

---

## 环境配置

### 1. 主网配置 (.env)

编辑项目根目录的 `.env` 文件：

```bash
# Binance 主网 API 凭证
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_api_secret_here
```

**示例**:
```bash
BINANCE_API_KEY=AbCdEfGhIjKlMnOpQrStUvWxYz1234567890
BINANCE_API_SECRET=1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ
```

### 2. Testnet 配置 (test.env)

编辑项目根目录的 `test.env` 文件：

```bash
# Binance Testnet API 凭证
BINANCE_TESTNET_API_KEY=your_binance_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_binance_testnet_api_secret_here
```

### 3. 环境配置文件

项目已提供 Binance sandbox 配置模板：

**config/environments/binance_sandbox.yaml**:
```yaml
sandbox:
  venue: "BINANCE"
  is_testnet: true

  instrument_ids:
    - "ETHUSDT-PERP.BINANCE"
    - "SOLUSDT-PERP.BINANCE"
    - "BNBUSDT-PERP.BINANCE"
    - "DOGEUSDT-PERP.BINANCE"

  api_key_env: "BINANCE_TESTNET_API_KEY"
  api_secret_env: "BINANCE_TESTNET_API_SECRET"
  api_passphrase_env: ""  # Binance 不需要 passphrase
```

### 4. 激活 Binance 环境

修改 `config/active.yaml`：

```yaml
# 使用 Binance sandbox 环境
environment: "binance_sandbox"

# 选择策略
strategy: "keltner_rs_breakout"
```

---

## Testnet 配置

### Testnet 特点

- ✅ **免费测试**: 无需真实资金
- ✅ **真实环境**: 模拟真实交易流程
- ✅ **无风险**: 测试策略不会造成实际损失
- ⚠️ **数据延迟**: Testnet 数据可能与主网略有差异
- ⚠️ **流动性**: Testnet 流动性较低

### Testnet 端点

Binance Testnet 使用不同的 API 端点：

- **Futures Testnet**: `https://testnet.binancefuture.com`
- **Spot Testnet**: `https://testnet.binance.vision`

NautilusTrader 会根据 `is_testnet: true` 自动切换到 Testnet 端点。

### 测试流程

1. **配置 test.env**
   ```bash
   BINANCE_TESTNET_API_KEY=your_testnet_key
   BINANCE_TESTNET_API_SECRET=your_testnet_secret
   ```

2. **运行 preflight 检查**
   ```bash
   python -m sandbox.preflight --env binance_sandbox
   ```

3. **启动 sandbox**
   ```bash
   python -m sandbox.engine
   ```

---

## 安全建议

### 🔒 API 密钥安全

1. **永远不要提交 .env 文件到 Git**
   - `.env` 和 `test.env` 已在 `.gitignore` 中
   - 检查提交前确保没有包含敏感信息

2. **使用 IP 白名单**
   - 在 Binance API 设置中限制访问 IP
   - 只允许你的服务器 IP 访问

3. **最小权限原则**
   - 只开启必需的 API 权限
   - **禁用提现权限**
   - 定期轮换 API 密钥

4. **监控 API 使用**
   - 定期检查 API 调用记录
   - 发现异常立即禁用 API Key

5. **使用子账户**（推荐）
   - 为交易机器人创建专用子账户
   - 限制子账户资金量
   - 降低主账户风险

### 🛡️ 环境隔离

```bash
# 开发环境 - 使用 Testnet
environment: "binance_sandbox"
is_testnet: true

# 生产环境 - 使用主网
environment: "live"
is_testnet: false
```

### 📊 风险控制

1. **初始资金限制**
   ```yaml
   trading:
     initial_balance: 1000  # 从小额开始
   ```

2. **仓位限制**
   ```yaml
   strategy:
     max_positions: 3
     qty_percent: 0.05  # 每次最多使用 5% 资金
   ```

3. **止损设置**
   ```yaml
   strategy:
     base_risk_pct: 0.01  # 每笔交易风险 1%
   ```

---

## 常见问题

### Q1: API Key 无效

**错误**: `Invalid API-key, IP, or permissions for action`

**解决方案**:
1. 检查 API Key 和 Secret 是否正确复制
2. 确认 API 权限已开启（Reading + Futures）
3. 检查 IP 白名单设置
4. 确认使用的是正确的环境（主网/测试网）

### Q2: Testnet 连接失败

**错误**: `Connection timeout` 或 `Network error`

**解决方案**:
1. 确认 Testnet 服务是否正常运行
2. 检查网络连接
3. 尝试访问 https://testnet.binancefuture.com 确认可访问
4. 检查防火墙设置

### Q3: 签名验证失败

**错误**: `Signature for this request is not valid`

**解决方案**:
1. 检查系统时间是否准确（时间偏差不能超过 5 秒）
2. 确认 Secret Key 没有多余的空格或换行
3. 检查 API Key 和 Secret 是否匹配

### Q4: 权限不足

**错误**: `This action is unauthorized`

**解决方案**:
1. 在 Binance API 管理页面检查权限设置
2. 确保开启了 "Enable Futures" 权限
3. 如果使用子账户，确认子账户有足够权限

### Q5: 如何切换主网和测试网？

**方案 1**: 修改 `config/active.yaml`
```yaml
# Testnet
environment: "binance_sandbox"

# 主网
environment: "live"
```

**方案 2**: 修改环境配置文件中的 `is_testnet`
```yaml
sandbox:
  is_testnet: true   # Testnet
  is_testnet: false  # 主网
```

### Q6: Preflight 检查失败

**错误**: `Preflight detected problems`

**解决方案**:
1. 运行 preflight 查看具体问题：
   ```bash
   python -m sandbox.preflight --env binance_sandbox
   ```
2. 根据错误提示逐项修复：
   - 环境文件缺失 → 检查 `.env` 或 `test.env`
   - API 变量未设置 → 检查环境变量名称
   - Instrument 文件缺失 → 设置 `allow_missing_instruments: true`

---

## 相关文档

- [Binance API 官方文档](https://binance-docs.github.io/apidocs/futures/en/)
- [NautilusTrader Binance 适配器](https://nautilustrader.io/docs/latest/integrations/binance.html)
- [项目异常系统指南](./EXCEPTION_SYSTEM_GUIDE.md)

---

## 支持

如有问题，请：
1. 查看本文档的常见问题部分
2. 检查项目日志文件 `log/` 目录
3. 提交 Issue 到项目仓库

**注意**: 提交 Issue 时，**绝对不要**包含你的 API Key 或 Secret！
