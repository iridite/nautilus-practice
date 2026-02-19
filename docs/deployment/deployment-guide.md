# Nautilus Practice 部署指南

本指南详细说明如何部署 Nautilus Practice 量化交易系统，包括环境配置、数据准备、配置管理和启动流程。

## 目录

- [系统要求](#系统要求)
- [环境配置](#环境配置)
- [数据准备](#数据准备)
- [配置文件](#配置文件)
- [启动流程](#启动流程)
- [监控和日志](#监控和日志)
- [常见问题排查](#常见问题排查)

---

## 系统要求

### 硬件要求

**最低配置**:
- CPU: 2 核
- 内存: 4 GB
- 硬盘: 20 GB 可用空间
- 网络: 稳定的互联网连接

**推荐配置**:
- CPU: 4 核或更多
- 内存: 8 GB 或更多
- 硬盘: 50 GB SSD
- 网络: 低延迟网络（< 100ms 到交易所）

### 软件要求

- **操作系统**: Linux (Ubuntu 20.04+), macOS (10.15+), Windows 10+
- **Python**: 3.12.12 或更高（严格要求 `>=3.12.12, <3.13`）
- **包管理器**: uv (推荐) 或 pip
- **Git**: 用于克隆仓库

---

## 环境配置

### 1. 安装 Python 3.12.12+

#### Ubuntu/Debian

```bash
# 添加 deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update

# 安装 Python 3.12
sudo apt install python3.12 python3.12-venv python3.12-dev

# 验证版本
python3.12 --version
```

#### macOS

```bash
# 使用 Homebrew
brew install python@3.12

# 验证版本
python3.12 --version
```

#### Windows

1. 下载 Python 3.12 安装包: https://www.python.org/downloads/
2. 运行安装程序，勾选 "Add Python to PATH"
3. 验证安装: `python --version`

### 2. 安装 uv 包管理器

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 验证安装
uv --version
```

### 3. 克隆项目

```bash
# 克隆仓库
git clone https://github.com/your-repo/nautilus-practice.git
cd nautilus-practice

# 查看项目结构
ls -la
```

### 4. 安装依赖

```bash
# 使用 uv 同步依赖
uv sync

# 激活虚拟环境（可选）
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# 验证安装
uv run python -c "import nautilus_trader; print(nautilus_trader.__version__)"
```

### 5. 验证安装

```bash
# 运行测试
uv run python -m unittest discover -s tests -p "test_*.py" -v

# 检查核心模块
uv run python -c "from strategy.core.base import BaseStrategy; print('✅ Strategy 模块正常')"
uv run python -c "from utils import get_project_root; print('✅ Utils 模块正常')"
```

---

## 数据准备

### 1. 目录结构

```bash
# 创建数据目录
mkdir -p data/{raw,parquet,instrument,universe,record,top}
mkdir -p log/{backtest,sandbox,archive}
mkdir -p output/backtest
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置文件
vim .env
```

**`.env` 文件示例**:
```bash
# 交易所 API 配置
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# OKX API 配置（可选）
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_PASSPHRASE=your_okx_passphrase

# 数据库配置（可选）
DATABASE_URL=postgresql://user:password@localhost:5432/nautilus

# 日志级别
LOG_LEVEL=INFO

# 其他配置
TIMEZONE=Asia/Shanghai
```

**⚠️ 安全提示**: 
- 永远不要将包含真实 API Key 的 `.env` 文件提交到版本控制
- `.env` 文件已在 `.gitignore` 中

### 3. 获取历史数据

#### 方法 1: 自动获取（推荐）

```bash
# 运行回测时自动下载数据
uv run python main.py backtest

# 系统会自动检测并下载缺失的数据
```

#### 方法 2: 手动获取

```bash
# 获取 OHLCV 数据
uv run python scripts/fetch_ohlcv.py \
    --symbols BTCUSDT ETHUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --timeframe 1h \
    --exchange binance

# 获取 OI 和 Funding Rate 数据
uv run python scripts/fetch_oi_funding.py \
    --symbols BTCUSDT ETHUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --exchange binance
```

### 4. 生成 Universe

```bash
# 生成交易对 Universe（用于策略过滤）
uv run python scripts/generate_universe.py \
    --top-n 50 \
    --freq ME \
    --start-date 2024-01-01 \
    --end-date 2024-12-31

# 输出: data/universe/universe_50_ME.json
```

### 5. 获取标的信息

```bash
# 获取交易所标的信息
uv run python scripts/fetch_instrument.py \
    --exchange binance \
    --symbols BTCUSDT ETHUSDT

# 输出: data/instrument/binance_instruments.json
```

### 6. 验证数据完整性

```bash
# 检查数据文件
uv run python scripts/verify_data.py \
    --symbols BTCUSDT ETHUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --timeframe 1h

# 输出数据统计
```

---

## 配置文件

### 1. 策略配置

策略配置文件位于 `config/strategies/` 目录。

#### 创建策略配置

```bash
# 复制模板
cp config/strategies/keltner_rs_backtest.yaml \
   config/strategies/my_strategy.yaml

# 编辑配置
vim config/strategies/my_strategy.yaml
```

#### 配置示例

```yaml
# config/strategies/keltner_rs_live.yaml

strategy:
  class: KeltnerRSBreakoutStrategy
  config:
    # 标的配置
    symbol: "ETHUSDT"
    timeframe: "1d"
    btc_symbol: "BTCUSDT"
    
    # 仓位管理
    use_atr_position_sizing: true
    base_risk_pct: 0.01
    high_conviction_risk_pct: 0.015
    leverage: 2
    max_positions: 1
    
    # 指标参数
    ema_period: 20
    atr_period: 20
    sma_period: 200
    
    # 通道参数
    keltner_base_multiplier: 1.5
    keltner_trigger_multiplier: 2.25
    
    # 风控参数
    stop_loss_atr_multiplier: 2.0
    enable_time_stop: true
    time_stop_bars: 3
    
    # 过滤器
    enable_btc_regime_filter: true
    enable_euphoria_filter: true
    
    # Universe
    universe_top_n: 50
    universe_freq: "ME"

# 交易所配置
exchange:
  name: "binance"
  api_key: "${BINANCE_API_KEY}"
  api_secret: "${BINANCE_API_SECRET}"
  testnet: false

# 风控配置
risk:
  max_daily_loss: 0.05      # 5% 日最大亏损
  max_drawdown: 0.20        # 20% 最大回撤
  emergency_stop: true
```

### 2. 环境配置

环境配置文件位于 `config/environments/` 目录。

```yaml
# config/environments/production.yaml

environment: production

# 日志配置
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "log/production.log"
  rotation: "1 day"
  retention: "30 days"

# 数据库配置
database:
  url: "${DATABASE_URL}"
  pool_size: 10
  max_overflow: 20

# 监控配置
monitoring:
  enabled: true
  prometheus_port: 9090
  health_check_interval: 60

# 告警配置
alerts:
  enabled: true
  channels:
    - type: telegram
      token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_CHAT_ID}"
    - type: email
      smtp_server: "smtp.gmail.com"
      smtp_port: 587
      from: "alerts@example.com"
      to: "admin@example.com"
```

### 3. 活跃配置

`config/active.yaml` 指定当前使用的配置。

```yaml
# config/active.yaml

# 当前环境
environment: production

# 当前策略
strategies:
  - keltner_rs_live
  - dual_thrust_live

# 数据源
data_sources:
  primary: binance
  fallback: okx

# 其他配置
timezone: "Asia/Shanghai"
log_level: INFO
```

---

## 启动流程

### 1. 回测模式

```bash
# 基本回测
uv run python main.py backtest

# 指定策略
uv run python main.py backtest --strategy keltner_rs_breakout

# 指定参数
uv run python main.py backtest \
    --symbol ETHUSDT \
    --start-date 2024-01-01 \
    --end-date 2024-12-31 \
    --timeframe 1d

# 跳过 OI 数据检查
uv run python main.py backtest --skip-oi-data

# 强制重新下载数据
uv run python main.py backtest --force-oi-fetch
```

### 2. 沙盒模式（模拟交易）

```bash
# 启动沙盒
uv run python main.py sandbox --config config/strategies/keltner_rs_sandbox.yaml

# 查看沙盒状态
uv run python cli/commands.py sandbox status

# 停止沙盒
uv run python cli/commands.py sandbox stop
```

### 3. 实盘模式

#### 启动前检查

```bash
# 1. 验证配置
uv run python cli/commands.py config validate

# 2. 检查 API 连接
uv run python cli/commands.py exchange test-connection

# 3. 检查账户余额
uv run python cli/commands.py account balance

# 4. 运行预检
uv run python cli/commands.py preflight
```

#### 启动实盘

```bash
# 前台运行（用于测试）
uv run python main.py live --config config/strategies/keltner_rs_live.yaml

# 后台运行（生产环境）
nohup uv run python main.py live \
    --config config/strategies/keltner_rs_live.yaml \
    > log/live.log 2>&1 &

# 查看进程
ps aux | grep "main.py live"

# 查看日志
tail -f log/live.log
```

#### 使用 systemd 管理（Linux）

创建 systemd 服务文件:

```bash
# /etc/systemd/system/nautilus-practice.service

[Unit]
Description=Nautilus Practice Trading Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/nautilus-practice
Environment="PATH=/path/to/nautilus-practice/.venv/bin"
ExecStart=/path/to/nautilus-practice/.venv/bin/python main.py live --config config/strategies/keltner_rs_live.yaml
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务:

```bash
# 重载 systemd
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start nautilus-practice

# 设置开机自启
sudo systemctl enable nautilus-practice

# 查看状态
sudo systemctl status nautilus-practice

# 查看日志
sudo journalctl -u nautilus-practice -f
```

---

## 监控和日志

### 1. 日志系统

#### 日志目录结构

```
log/
├── backtest/           # 回测日志
├── sandbox/            # 沙盒日志
├── live.log            # 实盘日志
├── archive/            # 归档日志
└── logrotate.conf      # 日志轮转配置
```

#### 查看日志

```bash
# 实时查看实盘日志
tail -f log/live.log

# 查看最近 100 行
tail -n 100 log/live.log

# 搜索错误
grep "ERROR" log/live.log

# 搜索特定策略
grep "KeltnerRSBreakout" log/live.log
```

#### 日志轮转

```bash
# 配置 logrotate
sudo vim /etc/logrotate.d/nautilus-practice

# 内容:
/path/to/nautilus-practice/log/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 your_username your_username
}

# 测试配置
sudo logrotate -d /etc/logrotate.d/nautilus-practice

# 强制轮转
sudo logrotate -f /etc/logrotate.d/nautilus-practice
```

### 2. 性能监控

#### 系统资源监控

```bash
# CPU 和内存使用
top -p $(pgrep -f "main.py live")

# 详细资源统计
htop

# 磁盘使用
df -h
du -sh data/*
```

#### 应用监控

```bash
# 查看持仓
uv run python cli/commands.py positions

# 查看订单
uv run python cli/commands.py orders

# 查看今日交易
uv run python cli/commands.py trades --today

# 查看账户状态
uv run python cli/commands.py account

# 查看策略状态
uv run python cli/commands.py strategy status
```

### 3. 告警系统

#### Telegram 告警

```python
# utils/alerts.py

import requests

def send_telegram_alert(message: str):
    """发送 Telegram 告警"""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"发送 Telegram 告警失败: {e}")
```

#### 邮件告警

```python
# utils/alerts.py

import smtplib
from email.mime.text import MIMEText

def send_email_alert(subject: str, body: str):
    """发送邮件告警"""
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    from_email = os.getenv("ALERT_FROM_EMAIL")
    to_email = os.getenv("ALERT_TO_EMAIL")
    password = os.getenv("EMAIL_PASSWORD")
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(from_email, password)
            server.send_message(msg)
    except Exception as e:
        logger.error(f"发送邮件告警失败: {e}")
```

---

## 常见问题排查

### 1. 安装问题

#### Q: uv sync 失败

```bash
# 清理缓存
uv cache clean

# 重新同步
uv sync

# 如果仍然失败，使用 pip
python -m pip install -r requirements.txt
```

#### Q: Python 版本不匹配

```bash
# 检查版本
python --version

# 使用特定版本
python3.12 -m venv .venv
source .venv/bin/activate
pip install uv
uv sync
```

### 2. 数据问题

#### Q: 数据下载失败

```bash
# 检查网络连接
ping api.binance.com

# 使用代理
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=http://proxy:port

# 重试下载
uv run python main.py backtest --force-oi-fetch --max-retries 5
```

#### Q: 数据格式错误

```bash
# 验证数据格式
uv run python scripts/verify_data.py --file data/raw/BTCUSDT_1h.csv

# 重新下载
rm data/raw/BTCUSDT_1h.csv
uv run python scripts/fetch_ohlcv.py --symbols BTCUSDT
```

### 3. 运行时问题

#### Q: 策略不开仓

**排查步骤**:

1. 检查日志
   ```bash
   grep "开仓" log/live.log
   grep "过滤" log/live.log
   ```

2. 启用调试日志
   ```python
   # 在策略中添加
   self.log.setLevel(logging.DEBUG)
   ```

3. 检查过滤条件
   ```python
   # 添加调试输出
   self.log.info(f"Universe 活跃: {self._is_symbol_active()}")
   self.log.info(f"BTC 市场状态: {self._check_btc_market_regime()}")
   ```

#### Q: 订单被拒绝

**可能原因**:

1. 余额不足
   ```bash
   uv run python cli/commands.py account balance
   ```

2. 数量不符合要求
   ```python
   # 检查最小数量
   print(f"Min qty: {instrument.size_increment}")
   print(f"Order qty: {qty}")
   ```

3. API 限流
   ```bash
   # 检查日志
   grep "rate limit" log/live.log
   ```

#### Q: 内存占用过高

```bash
# 检查内存使用
ps aux | grep python

# 清理历史数据
# 在策略中限制历史数据大小
config.max_history_size = 100

# 定期重启
sudo systemctl restart nautilus-practice
```

### 4. 网络问题

#### Q: API 连接超时

```bash
# 测试连接
curl -I https://api.binance.com/api/v3/ping

# 使用备用域名
# 在配置中设置
exchange:
  api_url: "https://api1.binance.com"
```

#### Q: WebSocket 断连

```python
# 启用自动重连
config.websocket_auto_reconnect = True
config.websocket_reconnect_delay = 5
```

### 5. 性能问题

#### Q: 回测速度慢

```bash
# 使用 Parquet 格式
uv run python scripts/convert_to_parquet.py

# 减少数据量
# 只加载必要的时间范围

# 使用多进程
uv run python main.py backtest --workers 4
```

#### Q: 实盘延迟高

```bash
# 检查网络延迟
ping api.binance.com

# 使用更近的服务器
# 考虑使用 VPS 部署

# 优化代码
# 减少不必要的计算
```

---

## 生产环境最佳实践

### 1. 安全性

- ✅ 使用环境变量存储敏感信息
- ✅ 定期更换 API Key
- ✅ 限制 API Key 权限（只开启交易权限）
- ✅ 使用 IP 白名单
- ✅ 启用 2FA

### 2. 可靠性

- ✅ 使用 systemd 管理进程
- ✅ 配置自动重启
- ✅ 设置健康检查
- ✅ 启用日志轮转
- ✅ 定期备份配置和数据

### 3. 监控

- ✅ 实时监控持仓和订单
- ✅ 设置告警阈值
- ✅ 监控系统资源
- ✅ 记录关键指标
- ✅ 定期审查日志

### 4. 风控

- ✅ 设置最大亏损限制
- ✅ 限制单笔交易风险
- ✅ 控制总持仓比例
- ✅ 启用紧急停止机制
- ✅ 定期检查策略表现

### 5. 维护

- ✅ 定期更新依赖
- ✅ 定期优化参数
- ✅ 定期清理日志
- ✅ 定期备份数据
- ✅ 定期审查代码

---

## 参考资料

- [项目 README](../../README.md)
- [Strategy API 文档](../api/strategy-api.md)
- [Utils API 文档](../api/utils-api.md)
- [Keltner RS Breakout 策略](../guides/keltner-rs-breakout.md)
- [Dual Thrust 策略](../guides/dual-thrust.md)

---

**最后更新**: 2026-02-19
**版本**: v2.1
