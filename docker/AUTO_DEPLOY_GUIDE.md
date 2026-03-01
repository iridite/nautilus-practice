# 完全自动化部署指南

本指南描述如何在**什么都没有**的情况下，从零开始自动部署并运行 Keltner 策略。

---

## 🎯 目标

在老家电脑（FnOS Debian + Docker）上实现：
- ✅ 自动下载市场数据（从 Binance 公开 API）
- ✅ 自动生成 Universe 文件
- ✅ 自动配置 Mihomo 代理
- ✅ 成功运行 sandbox 策略回测

---

## 📋 前置要求

### 硬件要求
- CPU: 2 核以上
- 内存: 4GB 以上
- 磁盘: 10GB 可用空间

### 软件要求
- ✅ Docker 已安装
- ✅ Docker Compose 已安装
- ✅ 可以访问 GitHub
- ✅ 可以访问 Binance API（通过代理）

---

## 🚀 部署步骤

### 方法 1：一键自动部署（推荐）⭐

```bash
# 1. 克隆代码
git clone https://github.com/iridite/nautilus-practice.git
cd nautilus-practice

# 2. 切换到正确的分支
git checkout fix/funding-arbitrage-code-review

# 3. 一键部署（完全自动化）
./docker/auto-deploy.sh
```

**脚本会自动完成**：
1. 创建 `.env` 配置文件
2. 创建必需的目录结构
3. 构建 Docker 镜像
4. 启动 Mihomo 代理
5. 启动 Nautilus 容器
6. 自动下载市场数据（BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT）
7. 自动生成 Universe 文件
8. 运行 Keltner 策略回测

---

### 方法 2：手动部署（了解细节）

#### 步骤 1：克隆代码

```bash
git clone https://github.com/iridite/nautilus-practice.git
cd nautilus-practice
git checkout fix/funding-arbitrage-code-review
```

#### 步骤 2：创建环境配置

```bash
cat > .env << 'EOF'
CLASH_SUBSCRIPTION_URL=https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1
NAUTILUS_ENV=sandbox
LOG_LEVEL=INFO
TZ=UTC
EOF
```

#### 步骤 3：创建目录结构

```bash
mkdir -p data/{raw,parquet,universe,instrument}
mkdir -p output/backtest/{result,report}
mkdir -p logs
```

#### 步骤 4：构建并启动

```bash
# 构建镜像
docker compose build

# 启动服务
docker compose up -d
```

---

## 📊 验证部署

### 1. 检查容器状态

```bash
docker compose ps
```

**预期输出**：
```
NAME                 STATUS              PORTS
mihomo-proxy         Up (healthy)        7890, 7891
nautilus-keltner     Up                  -
```

### 2. 查看实时日志

```bash
docker compose logs -f nautilus-keltner
```

**成功标志**：
```
[1/5] 等待 Mihomo 代理就绪...
✓ Mihomo 代理已就绪

[2/5] 检查数据文件...
  ✗ 缺失数据: BTCUSDT
开始下载缺失的数据...
下载 BTCUSDT 数据...
✓ 数据下载完成

[3/5] 检查 Universe 文件...
生成 Universe...
✓ Universe 生成完成

[4/5] 验证配置文件...
✓ 配置验证通过

[5/5] 启动策略...
开始执行 Sandbox 策略
```

### 3. 查看回测结果

```bash
# 等待回测完成（通常需要 5-10 分钟）
sleep 600

# 查看结果文件
ls -lh output/backtest/result/

# 查看最新结果
cat output/backtest/result/backtest_result_*.json | jq .
```

---

## 🔧 自动化流程详解

### 数据下载流程

entrypoint 脚本会自动：

1. **检查数据目录**：`data/raw/BTCUSDT`, `data/raw/ETHUSDT` 等
2. **如果数据缺失**：
   - 计算日期范围（最近 2 年）
   - 调用 `scripts/download_full_year_data.py`
   - 从 Binance 公开 API 下载 OHLCV 数据
   - 保存到 `data/raw/<SYMBOL>/` 目录
3. **如果数据存在**：跳过下载，直接使用

### Universe 生成流程

1. **检查 Universe 文件**：`data/universe/universe_15_W-MON.json`
2. **如果文件不存在**：
   - 调用 `scripts/generate_universe.py`
   - 根据市值、流动性等指标筛选 Top 15 交易对
   - 生成 Universe JSON 文件
3. **如果文件存在**：跳过生成，直接使用

### 代理配置流程

1. **等待 Mihomo 就绪**：检查 `mihomo:7890` 端口
2. **配置环境变量**：
   - `HTTP_PROXY=http://mihomo:7890`
   - `HTTPS_PROXY=http://mihomo:7890`
3. **验证连接**：使用 `nc` 命令测试代理可用性

---

## 📁 目录结构

部署完成后的目录结构：

```
nautilus-practice/
├── data/
│   ├── raw/                    # 原始 OHLCV 数据（自动下载）
│   │   ├── BTCUSDT/
│   │   ├── ETHUSDT/
│   │   └── ...
│   ├── parquet/                # Parquet 缓存（自动生成）
│   ├── universe/               # Universe 文件（自动生成）
│   │   └── universe_15_W-MON.json
│   └── instrument/             # 交易对配置（volume 挂载）
├── output/
│   └── backtest/
│       ├── result/             # 回测结果 JSON
│       └── report/             # 回测报告
├── logs/                       # 日志文件
├── config/                     # 配置文件（只读）
└── .env                        # 环境变量（自动创建）
```

---

## 🔄 更新和维护

### 更新代码

```bash
# 拉取最新代码
git pull origin fix/funding-arbitrage-code-review

# 重新构建镜像
docker compose build

# 重启服务
docker compose down
docker compose up -d
```

### 清理旧数据

```bash
# 清理 7 天前的回测结果
find output/backtest/result/ -name "*.json" -mtime +7 -delete

# 清理 Parquet 缓存（强制重新生成）
rm -rf data/parquet/*
```

### 重新下载数据

```bash
# 删除旧数据
rm -rf data/raw/*

# 重启容器（会自动重新下载）
docker compose restart nautilus-keltner
```

---

## 🐛 故障排查

### 问题 1：代理连接失败

**症状**：
```
代理未就绪，等待 5 秒...
���误: 代理未就绪，超时退出
```

**解决**：
```bash
# 检查 Mihomo 日志
docker compose logs mihomo

# 测试订阅链接
curl -I "https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1"

# 重启代理
docker compose restart mihomo
```

### 问题 2：数据下载失败

**症状**：
```
警告: BTCUSDT 下载失败，将跳过
```

**解决**：
```bash
# 手动下载数据
docker compose exec nautilus-keltner python scripts/download_full_year_data.py \
  --symbols BTCUSDT \
  --start-date 2024-01-01 \
  --end-date 2026-01-01

# 或者在宿主机上下载后复制进容器
# （需要先安装 Python 环境）
```

### 问题 3：Universe 生成失败

**症状**：
```
警告: Universe 生成失败，将使用默认配置
```

**解决**：
```bash
# 手动生成 Universe
docker compose exec nautilus-keltner python scripts/generate_universe.py \
  --top-n 15 \
  --freq W-MON \
  --output data/universe/universe_15_W-MON.json
```

### 问题 4：内存不足

**症状**：
```
Killed (OOM)
```

**解决**：
编辑 `docker-compose.yml`，降低内存限制：
```yaml
nautilus-keltner:
  deploy:
    resources:
      limits:
        memory: 4G  # 从 8G 降到 4G
```

### 问题 5：配置文件缺失

**症状**：
```
错误: 配置文件缺失: config/strategies/keltner_rs_breakout.yaml
```

**解决**：
```bash
# 确保配置文件存在
ls -la config/strategies/
ls -la config/environments/

# 如果缺失，从 Git 重新拉取
git checkout config/
```

---

## 📈 性能优化

### 加速数据下载

1. **使用代理**：确保 Mihomo 正常工作
2. **并行下载**：修改脚本支持多线程下载
3. **使用缓存**：保留 `data/raw/` 目录，避免重复下载

### 减少内存使用

1. **降低 Universe 大小**：从 15 改为 10
2. **使用更短的回测周期**：从 2 年改为 1 年
3. **降低容器内存限制**：从 8G 改为 4G

---

## 🎯 下一步

部署成功后：

1. **切换到实盘模式**：
   ```bash
   # 编辑 .env
   NAUTILUS_ENV=live

   # 重启服务
   docker compose down && docker compose up -d
   ```

2. **定期执行回测**：
   ```bash
   # 添加 cron 任务（每天凌晨 2 点）
   0 2 * * * cd /path/to/nautilus-practice && docker compose up
   ```

3. **监控服务状态**：
   ```bash
   # 查看容器健康状态
   docker compose ps

   # 查看资源使用
   docker stats
   ```

---

## 📞 获取帮助

- 快速开始：`docker/QUICK_START.md`
- 发布指南：`docker/PUBLISH_GUIDE.md`
- 部署流程：`docker/DEPLOYMENT_WORKFLOW.md`
- 项目文档：`docker/README.md`

---

## ✅ 验证清单

部署完成后，确认以下项目：

- [ ] Mihomo 代理容器运行正常（`docker compose ps`）
- [ ] Nautilus 容器运行正常
- [ ] 数据目录包含至少 5 个交易对的数据
- [ ] Universe 文件已生成
- [ ] 回测成功完成
- [ ] 结果文件存在于 `output/backtest/result/`
- [ ] 日志没有严重错误

---

## 🎉 成功标志

当你看到以下输出时，说明部署成功：

```
✓ Mihomo 代理已就绪
✓ 所有必需数据已存在
✓ Universe 文件已存在
✓ 配置验证通过
开始执行 Sandbox 策略
```

恭喜！你已经成功部署了完全自动化的 Nautilus Keltner 策略系统。
