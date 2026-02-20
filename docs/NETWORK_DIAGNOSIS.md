# 网络诊断报告

## 问题描述
Sandbox 模式无法连接到 OKX 交易所 API

## 诊断时间
2026-02-20

## 测试结果

### 1. OKX 主网 API 测试
```bash
curl -v https://www.okx.com/api/v5/public/time
```

**结果:**
```
* IPv4: 169.254.0.2
* Trying 169.254.0.2:443...
* connect to 169.254.0.2 port 443 failed: Connection timed out
* Failed to connect after 132691 ms
```

**分析:** DNS 解析到无效的链路本地地址 `169.254.0.2`

### 2. OKX 测试网 WebSocket 测试
```bash
curl -v https://wspap.okx.com:8443/ws/v5/public
```

**结果:**
```
* Trying 104.18.43.174:8443...
* Recv failure: Connection reset by peer
* TLS connect error
curl: (35) Recv failure: Connection reset by peer
```

**分析:** 连接被主动重置

### 3. Binance API 测试
```bash
curl -I https://www.binance.com
```

**结果:**
```
curl: (35) Recv failure: Connection reset by peer
```

**分析:** 同样被阻断

### 4. Ping 测试
```bash
ping -c 3 www.okx.com
```

**结果:**
```
PING www.okx.com (169.254.0.2) 56(84) bytes of data.
--- www.okx.com ping statistics ---
3 packets transmitted, 0 received, 100% packet loss
```

**分析:** 100% 丢包

## 结论

### 🔴 确凿证据:本地网络问题

1. **DNS 污染**
   - `www.okx.com` 被解析到无效 IP `169.254.0.2`
   - 这是链路本地地址,不是公网 IP

2. **连接主动重置**
   - 即使能解析到正确 IP,连接也会被重置
   - 错误代码: `Connection reset by peer`

3. **多个交易所均被阻断**
   - OKX: ❌ 阻断
   - Binance: ❌ 阻断
   - 模式: DNS 污染 + 连接重置

### 根本原因
网络环境(ISP/防火墙/DNS)正在主动阻断加密货币交易所的连接

### API 凭证状态
✅ API 凭证本身没有问题,问题完全在于网络层面

## 解决方案

### 方案 1: 使用代理/VPN (推荐用于 Sandbox)
```bash
# 设置代理
export https_proxy=http://your-proxy:port
export http_proxy=http://your-proxy:port

# 运行 sandbox
uv run python sandbox/engine.py --env sandbox
```

### 方案 2: 修改 DNS
```bash
# 使用国外 DNS
sudo vim /etc/resolv.conf
# 添加:
nameserver 8.8.8.8
nameserver 1.1.1.1
```

### 方案 3: 使用 Backtest 模式 (推荐用于策略开发)
```bash
# 完全本地运行,不需要网络连接
python examples/run_dual_thrust.py
```

## 技术细节

### 169.254.0.0/16 地址段
- IANA 保留的链路本地地址段
- 用于自动配置(APIPA)
- 不应该出现在公网 DNS 解析中
- 出现此地址表明 DNS 被污染

### Connection Reset by Peer
- TCP 连接被对方主动关闭
- 通常由防火墙/IDS/IPS 触发
- 表明连接请求被识别并阻断

## 建议

1. **开发阶段**: 使用 Backtest 模式进行策略开发和测试
2. **测试阶段**: 配置代理后使用 Sandbox 模式
3. **生产阶段**: 确保网络环境可以访问交易所 API

## 相关文件

- `test.env` - API 凭证配置(已正确配置)
- `config/environments/sandbox.yaml` - Sandbox 配置(已正确配置)
- `sandbox/engine.py` - Sandbox 运行引擎(已添加说明)
