# Keltner 策略回测系统 Docker 部署文档

## 1. 概述

本项目是基于 NautilusTrader 框架的 Keltner 策略回测系统，支持 Docker 容器化部署。

### 核心特性
- **双模式支持**：sandbox（沙盒测试）和 live（实盘交易）
- **Mihomo 代理集成**：自动配置 Clash 代理，解决网络访问限制
- **自动化运行**：一键启动，自动执行回测并输出结果
- **数据持久化**：回测结果、日志、缓存数据自动保存
- **资源优化**：多阶段构建，镜像体积 < 1GB

### 架构概览
```
nautilus-keltner --HTTP_PROXY--> mihomo --Internet--> Binance API
```

## 2. 前置要求

### 软件依赖
- Docker 20.10+
- Docker Compose 2.0+

### 硬件要求
- **最小配置**：4 CPU, 8GB RAM, 10GB 磁盘
- **推荐配置**：8 CPU, 16GB RAM, 50GB 磁盘

### 网络要求
- Clash 订阅链接（从代理服务商获取）
- 互联网连接（用于下载 Docker 镜像和数据）

## 3. 快速开始

### 3.1 克隆代码
```bash
git clone <repo-url>
cd nautilus-practice
```

### 3.2 配置环境变量
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入实际配置
nano .env
```

**必需配置**：
```bash
# Clash 订阅链接（必需）
CLASH_SUBSCRIPTION_URL=https://your-proxy-provider.com/clash/subscription

# 运行模式（sandbox 或 live）
NAUTILUS_ENV=sandbox

# 日志级别
LOG_LEVEL=DEBUG

# 时区
TZ=UTC
```

### 3.3 构建并启动
```bash
# 构建镜像并启动服务
docker-compose up --build

# 或者后台运行
docker-compose up --build -d
```

### 3.4 查看日志
```bash
# 实时查看所有服务日志
docker-compose logs -f

# 只查看主应用日志
docker-compose logs -f nautilus-keltner

# 只查看代理日志
docker-compose logs -f mihomo
```

### 3.5 查看结果
```bash
# 查看回测结果文件
ls -lh output/backtest/result/

# 查看最新结果
cat output/backtest/result/backtest_result_*.json | jq .
```

## 4. 配置说明

### 4.1 环境变量

| 变量名 | 说明 | 默认值 | 必需 |
|--------|------|--------|------|
| `CLASH_SUBSCRIPTION_URL` | Clash 订阅链接 | - | ✅ |
| `NAUTILUS_ENV` | 运行模式（sandbox/live） | sandbox | ❌ |
| `LOG_LEVEL` | 日志级别（DEBUG/INFO/WARNING/ERROR） | DEBUG | ❌ |
| `TZ` | 时区 | UTC | ❌ |

### 4.2 数据目录

| 目录 | 说明 | 权限 |
|------|------|------|
| `data/` | 原始数据和 Parquet 缓存 | 读写 |
| `output/` | 回测结果和报告 | 读写 |
| `logs/` | 应用日志 | 读写 |
| `config/` | 策略配置文件 | 只读 |

**目录结构**：
```
nautilus-practice/
├── data/
│   ├── raw/              # 原始 CSV 数据
│   ├── parquet/          # Parquet 缓存（10x 加速）
│   └── instrument/       # 交易对配置
├── output/
│   ├── backtest/
│   │   ├── result/       # JSON 结果文件
│   │   └── report/       # HTML 报告
│   └── logs/             # 应用日志
└── config/
    ├── active.yaml       # 活动配置
    ├── environments/     # 环境配置
    └── strategies/       # 策略参数
```

### 4.3 资源限制

| 服务 | CPU | 内存 | 说明 |
|------|-----|------|------|
| mihomo | 0.5 | 512MB | 代理服务 |
| nautilus-keltner | 4 | 8GB | 主应用 |

**调整资源限制**：
编辑 `docker-compose.yml` 中的 `deploy.resources.limits` 部分。

### 4.4 代理配置

Mihomo 代理服务端口：
- **7890**：HTTP 代理
- **7891**：SOCKS5 代理
- **9090**：API/Dashboard

代理规则（自动配置）：
- `binance.com` → PROXY
- `binance.us` → PROXY
- 其他域名 → DIRECT

## 5. 常用命令

### 5.1 容器管理
```bash
# 构建镜像（不启动）
docker-compose build

# 启动服务（前台）
docker-compose up

# 启动服务（后台）
docker-compose up -d

# 查看容器状态
docker-compose ps

# 停止服务
docker-compose down

# 停止并删除所有数据卷
docker-compose down -v
```

### 5.2 日志查看
```bash
# 查看所有日志
docker-compose logs

# 实时跟踪日志
docker-compose logs -f

# 查看最近 100 行日志
docker-compose logs --tail=100

# 查看特定服务���志
docker-compose logs nautilus-keltner
```

### 5.3 调试命令
```bash
# 进入容器 shell
docker-compose exec nautilus-keltner bash

# 查看容器资源使用
docker stats

# 查看容器详细信息
docker inspect nautilus-keltner

# 重启特定服务
docker-compose restart nautilus-keltner
```

### 5.4 数据管理
```bash
# 清理旧的回测结果
rm -rf output/backtest/result/*.json

# 清理 Parquet 缓存（强制重新生成）
rm -rf data/parquet/*

# 备份回测结果
tar -czf backtest-results-$(date +%Y%m%d).tar.gz output/

# 清理 Docker 缓存
docker system prune -a
```

## 6. 故障排查

### 6.1 代理连接失败

**症状**：
```
代理未就绪，等待 5 秒...
ERROR: Failed to connect to proxy after 3 retries
```

**可能原因**：
1. Clash 订阅链接无效或过期
2. 代理节点不可用
3. 网络连接问题
4. Mihomo 容器未启动

**解决方案**：

1. **检查订阅链接**：
```bash
# 测试订阅链接是否可访问
curl -I "${CLASH_SUBSCRIPTION_URL}"

# 应该返回 HTTP 200
```

2. **检查 Mihomo 容器状态**：
```bash
docker-compose ps mihomo

# 应该显示 "Up" 状态
```

3. **查看 Mihomo 日志**：
```bash
docker-compose logs mihomo

# 查找错误信息
```

4. **手动测试代理**：
```bash
# 进入主应用容器
docker-compose exec nautilus-keltner bash

# 测试代理连接
curl -x http://mihomo:7890 https://api.binance.com/api/v3/ping
```

5. **更换订阅链接**：
   - 联系代理服务商获取新链接
   - 更新 `.env` 文件
   - 重启服务：`docker-compose restart`

### 6.2 配置验证失败

**症状**：
```
ERROR: Config files not found!
ERROR: 配置验证失败
```

**可能原因**：
1. YAML 配置格式错误
2. 缺少必需的配置项
3. 配置值类型不匹配
4. 配置文件路径错误

**解决方案**：

1. **检查配置文件是否存在**：
```bash
ls -l config/active.yaml
ls -l config/environments/sandbox.yaml
ls -l config/strategies/keltner_rs_breakout.yaml
```

2. **验证 YAML 格式**：
```bash
# 使用 Python 验证 YAML
python -c "import yaml; yaml.safe_load(open('config/active.yaml'))"
```

3. **参考示例配置**：
```bash
# 查看开发环境配置示例
cat config/environments/dev.yaml
```

4. **检查配置挂载**：
```bash
# 查看容器内配置文件
docker-compose exec nautilus-keltner ls -l /app/config/
```

### 6.3 回测执行失败

**症状**：
```
容器退出码非 0
ERROR: Backtest execution failed
```

**可能原因**：
1. 数据文件缺失
2. 策略参数错误
3. 内存不足
4. 依赖包版本冲突

**解决方案**：

1. **检查数据文件**：
```bash
# 查看原始数据
ls -lh data/raw/

# 应该有 CSV 文件
```

2. **检查策略配置**：
```bash
cat config/strategies/keltner_rs_breakout.yaml

# 验证参数范围是否合理
```

3. **增加内存限制**：
```yaml
# 编辑 docker-compose.yml
services:
  nautilus-keltner:
    deploy:
      resources:
        limits:
          memory: 16G  # 从 8G 增加到 16G
```

4. **查看完整错误日志**：
```bash
docker-compose logs --tail=200 nautilus-keltner
```

5. **在容器内手动运行**：
```bash
docker-compose exec nautilus-keltner bash
python main.py backtest --type high
```

### 6.4 磁盘空间不足

**症状**：
```
ERROR: No space left on device
docker: write /var/lib/docker/...: no space left on device
```

**解决方案**：

1. **清理旧的回测结果**：
```bash
# 删除 7 天前的结果
find output/backtest/result/ -name "*.json" -mtime +7 -delete
```

2. **清理 Docker 缓存**：
```bash
# 清理未使用的镜像、容器、网络
docker system prune -a

# 清理未使用的数据卷
docker volume prune
```

3. **清理 Parquet 缓存**：
```bash
# Parquet 缓存可以重新生成
rm -rf data/parquet/*
```

4. **检查磁盘使用情况**：
```bash
df -h
du -sh data/ output/ logs/
```

### 6.5 容器无法启动

**症状**：
```
ERROR: Container failed to start
ERROR: Health check failed
```

**解决方案**：

1. **查看容器日志**：
```bash
docker-compose logs nautilus-keltner
```

2. **检查端口冲突**：
```bash
# 检查端口是否被占用
netstat -tuln | grep -E '7890|7891|9090'
```

3. **重建容器**：
```bash
docker-compose down
docker-compose up --build --force-recreate
```

4. **检查 Docker 守护进程**：
```bash
systemctl status docker
```

## 7. 高级配置

### 7.1 切换到 live 模式

**警告**：live 模式会连接真实交易所，请确保策略已充分测试。

```bash
# 1. 修改 .env 文件
NAUTILUS_ENV=live

# 2. 检查 live 环境配置
cat config/environments/live.yaml

# 3. 重启服务
docker-compose down
docker-compose up -d

# 4. 监控日志
docker-compose logs -f nautilus-keltner
```

### 7.2 自定义策略参数

编辑策略配置文件：
```bash
nano config/strategies/keltner_rs_breakout.yaml
```

**关键参数**：
```yaml
keltner_trigger_multiplier: 2.0  # Keltner 通道触发倍数
deviation_threshold: 0.30        # 偏离阈值
stop_loss_atr_multiplier: 2.5    # 止损 ATR 倍数
universe_top_n: 15               # 交易标的数量
```

修改后重启服务：
```bash
docker-compose restart nautilus-keltner
```

### 7.3 定期执行回测

使用 cron 定时任务：

```bash
# 编辑 crontab
crontab -e

# 添加定时任务（每天凌晨 2 点执行）
0 2 * * * cd /path/to/nautilus-practice && docker-compose up >> /var/log/nautilus-backtest.log 2>&1

# 每周一凌晨 3 点执行
0 3 * * 1 cd /path/to/nautilus-practice && docker-compose up

# 每月 1 号凌晨 4 点执行
0 4 1 * * cd /path/to/nautilus-practice && docker-compose up
```

### 7.4 自定义 Docker 镜像

如果需要修改 Dockerfile：

```bash
# 编辑 Dockerfile
nano Dockerfile

# 重新构建镜像
docker-compose build --no-cache

# 启动服务
docker-compose up
```

### 7.5 多环境部署

创建不同的 docker-compose 文件：

```bash
# 开发环境
docker-compose -f docker-compose.dev.yml up

# 生产环境
docker-compose -f docker-compose.prod.yml up

# 测试环境
docker-compose -f docker-compose.test.yml up
```

## 8. 安全建议

### 8.1 敏感信息保护
1. **不要提交 .env 文件到 Git**
   - `.env` 已在 `.gitignore` 中排除
   - 使用 `.env.example` 作为模板

2. **保护 Clash 订阅链接**
   - 不要在公开场合分享
   - 定期更换订阅链接
   - 使用环境变量而非硬编码

3. **限制文件权限**
```bash
chmod 600 .env
chmod 600 config/environments/live.yaml
```

### 8.2 网络安全
1. **限制容器网络访问**
   - 仅通过代理访问外部网络
   - 使用 Docker 网络隔离

2. **关闭不必要的端口**
```yaml
# docker-compose.yml
services:
  mihomo:
    ports:
      # 注释掉不需要的端口
      # - "9090:9090"  # Dashboard
```

3. **使用防火墙规则**
```bash
# 只允许本地访问
ufw allow from 127.0.0.1 to any port 7890
```

### 8.3 数据安全
1. **定期备份回测结果**
```bash
# 每周备份
tar -czf backtest-backup-$(date +%Y%m%d).tar.gz output/
```

2. **加密敏感数据**
```bash
# 使用 GPG 加密备份
gpg -c backtest-backup.tar.gz
```

3. **限制日志大小**
```yaml
# docker-compose.yml
services:
  nautilus-keltner:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### 8.4 访问控制
1. **使用强密码保护远程机器**
2. **配置 SSH 密钥认证**
3. **禁用 root 登录**
4. **定期更新系统和 Docker**

## 9. 性能优化

### 9.1 使用 Parquet 缓存
首次运行后，Parquet 缓存会自动生成，后续运行速度提升 10 倍。

```bash
# 查看缓存大小
du -sh data/parquet/

# 强制重新生成缓存
rm -rf data/parquet/*
docker-compose up
```

### 9.2 调整资源限制
根据目标机器规格调整 CPU 和内存：

```yaml
# docker-compose.yml
services:
  nautilus-keltner:
    deploy:
      resources:
        limits:
          cpus: '8'      # 增加 CPU
          memory: 16G    # 增加内存
```

### 9.3 使用高级引擎
高级引擎比低级引擎快 32%：

```bash
# 默认使用高级引擎
docker-compose up

# 或显式指定
docker-compose run nautilus-keltner backtest --type high
```

### 9.4 分批回测
如果全年回测超时，可以分季度执行：

```bash
# Q1 回测
docker-compose run nautilus-keltner backtest --start 2024-01-01 --end 2024-03-31

# Q2 回测
docker-compose run nautilus-keltner backtest --start 2024-04-01 --end 2024-06-30

# Q3 回测
docker-compose run nautilus-keltner backtest --start 2024-07-01 --end 2024-09-30

# Q4 回测
docker-compose run nautilus-keltner backtest --start 2024-10-01 --end 2024-12-31
```

### 9.5 并行执行
使用多个容器并行回测不同策略：

```bash
# 启动多个实例
docker-compose up --scale nautilus-keltner=4
```

## 10. 监控与告警

### 10.1 日志监控
使用 `tail` 实时监控日志：

```bash
# 监控错误日志
docker-compose logs -f | grep ERROR

# 监控警告日志
docker-compose logs -f | grep WARNING

# 监控交易信号
docker-compose logs -f | grep "SIGNAL"
```

### 10.2 资源监控
```bash
# 实时监控容器资源使用
docker stats

# 查看容器详细信息
docker inspect nautilus-keltner | jq '.[0].State'
```

### 10.3 健康检查
```bash
# 查看健康状态
docker-compose ps

# 手动触发健康检查
docker exec nautilus-keltner python -c "import sys; sys.exit(0)"
```

### 10.4 告警配置
集成外部告警系统（需要额外配置）：

```bash
# 发送邮件告警
echo "Backtest completed" | mail -s "Nautilus Alert" user@example.com

# 发送 Telegram 消息
curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
  -d chat_id=<CHAT_ID> \
  -d text="Backtest completed"

# 发送 Slack 消息
curl -X POST <WEBHOOK_URL> \
  -H 'Content-Type: application/json' \
  -d '{"text":"Backtest completed"}'
```

## 11. 支持与文档

### 11.1 项目文档
- **开发指南**：`CLAUDE.md`
- **技术规格**：`.omc/autopilot/spec.md`
- **架构决策**：`docs/lessons-learned/ARCHITECTURE_DECISIONS.md`
- **Git 工作流**：`docs/lessons-learned/GIT_WORKFLOW.md`

### 11.2 问题反馈
- **GitHub Issues**：提交 bug 报告和功能请求
- **Pull Requests**：贡献代码和文档改进

### 11.3 常见问题
1. **Q: 为什么需要 Clash 订阅链接？**
   - A: 用于访问 Binance API，解决网络限制问题。

2. **Q: sandbox 和 live 模式有什么区别？**
   - A: sandbox 使用模拟数据测试策略，live 连接真实交易所。

3. **Q: 如何查看回测结果？**
   - A: 结果保存在 `output/backtest/result/` 目录，使用 `jq` 查看 JSON 文件。

4. **Q: 如何修改策略参数？**
   - A: 编辑 `config/strategies/keltner_rs_breakout.yaml`，然后重启服务。

5. **Q: 如何清理旧数据？**
   - A: 删除 `output/` 和 `data/parquet/` 目录内容。

### 11.4 联系方式
- **项目维护者**：[GitHub Profile]
- **技术支持**：[Email/Telegram]

---

**文档版本**：v1.0
**更新时间**：2026-03-01
**适用版本**：NautilusTrader Practice v1.0+

## 附录

### A. 完整配置示例

**docker-compose.yml**：
```yaml
version: '3.8'

services:
  mihomo:
    image: metacubex/mihomo:latest
    container_name: mihomo-proxy
    ports:
      - "7890:7890"
      - "7891:7891"
      - "9090:9090"
    volumes:
      - ./docker/mihomo-config.yaml:/root/.config/mihomo/config.yaml:ro
    environment:
      - CLASH_SUBSCRIPTION_URL=${CLASH_SUBSCRIPTION_URL}
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9090"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    networks:
      - nautilus-network

  nautilus-keltner:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: nautilus-keltner
    depends_on:
      mihomo:
        condition: service_healthy
    environment:
      - HTTP_PROXY=http://mihomo:7890
      - HTTPS_PROXY=http://mihomo:7890
      - NAUTILUS_ENV=${NAUTILUS_ENV:-sandbox}
      - LOG_LEVEL=DEBUG
      - TZ=UTC
    volumes:
      - ./data:/app/data
      - ./output:/app/output
      - ./logs:/app/logs
      - ./config:/app/config:ro
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
    restart: "no"
    networks:
      - nautilus-network

networks:
  nautilus-network:
    driver: bridge
```

**.env 示例**：
```bash
CLASH_SUBSCRIPTION_URL=https://your-proxy-provider.com/clash/subscription
NAUTILUS_ENV=sandbox
LOG_LEVEL=DEBUG
TZ=UTC
```

### B. 故障排查检查清单

- [ ] Clash 订阅链接是否有效
- [ ] Mihomo 容器是否正常运行
- [ ] 代理连接是否可用
- [ ] 配置文件是否存在且格式正确
- [ ] 数据文件是否完整
- [ ] 磁盘空间是否充足
- [ ] 内存是否足够
- [ ] Docker 守护进程是否正常
- [ ] 网络连接是否正常
- [ ] 日志中是否有错误信息

### C. 性能基准

| 指标 | 低级引擎 | 高级引擎 | 改进 |
|------|----------|----------|------|
| 总执行时间 | 360.92s | 272.45s | +32% |
| 数据加载 | 慢 | 快 10x | Parquet 缓存 |
| 内存使用 | 中等 | 中等 | 相似 |
| CPU 使用 | 高 | 高 | 相似 |

### D. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v1.0 | 2026-03-01 | 初始版本，支持 Docker 部署 |
