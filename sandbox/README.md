# Sandbox 实时交易框架

统一的 Sandbox 运行框架，基于 YAML 配置文件快速启动实时交易环境。

## 使用方法

```bash
# 使用默认环境（从 config/active.yaml 读取）
python sandbox/engine.py

# 指定环境
python sandbox/engine.py --env sandbox
```

## 配置要求

### 1. 环境配置文件

在 `config/environments/` 目录下创建环境配置，必须包含 `sandbox` 配置块：

```yaml
# config/environments/sandbox.yaml
extends: "base.yaml"

sandbox:
  venue: "OKX"
  is_testnet: true  # true=测试网, false=主网

  instrument_ids:
    - "BTC-USDT-SWAP.OKX"

  api_key_env: "OKX_API_KEY"
  api_secret_env: "OKX_API_SECRET"
  api_passphrase_env: "OKX_API_PASSPHRASE"

  reconciliation: true
  reconciliation_lookback_mins: 1440
  filter_position_reports: true
  flush_cache_on_start: false
```

### 2. API 凭证配置

根据 `is_testnet` 设置，在对应的环境变量文件中配置 API 凭证：

**测试网模式** (`is_testnet: true`)：
- 文件：`test.env`
- 申请地址：https://www.okx.com/account/my-api (切换到测试网)

**主网模式** (`is_testnet: false`)：
- 文件：`.env`
- 申请地址：https://www.okx.com/account/my-api

环境变量格式：
```bash
OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_api_secret_here
OKX_API_PASSPHRASE=your_passphrase_here
```

### 3. 策略配置

在 `config/strategies/` 目录下配置策略参数。框架会自动注入 `instrument_id` 参数。

### 4. Instrument 数据文件

确保在 `data/instrument/{VENUE}/` 目录下存在对应的标的 JSON 文件：
- 例如：`data/instrument/OKX/BTC-USDT-SWAP.json`

## 注意事项

1. **单标的限制**：当前版本仅支持单个交易标的
2. **API 权限**：确保 API Key 具有交易权限
3. **测试网资金**：测试网账户需要先申请测试资金
4. **日志位置**：日志保存在 `log/sandbox/{trader_name}/runtime/`

## 故障排查

### 错误：Missing API credentials in environment
- 检查环境变量文件是否存在（test.env 或 .env）
- 检查 API 凭证是否正确配置
- 检查环境变量名称是否与配置文件中的 `api_key_env` 等字段匹配

### 错误：Environment does not have sandbox configuration
- 检查环境配置文件中是否包含 `sandbox` 配置块
- 检查 `config/active.yaml` 中的 `environment` 字段是否指向正确的环境

### 错误：Instrument file not found
- 检查 `data/instrument/{VENUE}/` 目录下是否存在对应的 JSON 文件
- 使用 `scripts/fetch_instrument.py` 获取标的数据
