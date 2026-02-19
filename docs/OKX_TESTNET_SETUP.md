# OKX 测试网 API 申请指南

## 步骤 1: 访问 OKX 测试网

1. 打开浏览器访问: https://www.okx.com/account/my-api
2. 登录你的 OKX 账户
3. **切换到测试网模式** (页面右上角有切换按钮)

## 步骤 2: 创建测试网 API Key

1. 点击 "Create API Key" 或 "创建 API"
2. 填写以下信息:
   - **API Key 名称**: nautilus-practice-testnet
   - **权限**: 
     - ✅ 读取 (Read)
     - ✅ 交易 (Trade)
     - ❌ 提现 (Withdraw) - 不需要
   - **IP 白名单**: 留空或填写你的服务器 IP
   - **Passphrase**: 设置一个密码（自己记住）

3. 点击确认后会显示:
   - API Key
   - Secret Key
   - Passphrase

⚠️ **重要**: Secret Key 只显示一次，务必保存！

## 步骤 3: 申请测试资金

1. 在测试网模式下，访问资产页面
2. 找到 "申请测试资金" 或 "Faucet" 按钮
3. 申请 USDT 测试币（通常可以申请 10,000 - 100,000 USDT）

## 步骤 4: 配置到项目

```bash
# 编辑 test.env
cd ~/Projects/nautilus-practice
nano test.env
```

填写内容:
```bash
# OKX Testnet API 凭证
OKX_API_KEY=你的API_Key
OKX_API_SECRET=你的Secret_Key
OKX_API_PASSPHRASE=你的Passphrase
```

保存后验证:
```bash
cat test.env | grep -v "^#" | grep -v "^$"
```

## 步骤 5: 测试连接

```bash
cd ~/Projects/nautilus-practice
.venv/bin/python -c "
import os
from dotenv import load_dotenv
load_dotenv('test.env')
print('API Key:', os.getenv('OKX_API_KEY')[:8] + '...')
print('API Secret:', os.getenv('OKX_API_SECRET')[:8] + '...')
print('Passphrase:', '***')
"
```

## 步骤 6: 启动 Sandbox

```bash
.venv/bin/python sandbox/engine.py --env sandbox
```

---

## 常见问题

### Q: 找不到测试网切换按钮？
A: 有些地区可能需要先在主网创建 API，然后才能看到测试网选项。

### Q: 测试资金申请失败？
A: 测试网可能有申请限制（每天/每周），稍后再试。

### Q: API 连接失败？
A: 检查:
1. API Key 是否正确复制（没有多余空格）
2. 是否在测试网模式下创建的 API
3. 权限是否包含 "Trade"

---

**准备好后告诉我，我帮你启动测试！**
