# 部署检查清单

## ✅ 已完成

1. ✅ Docker 配置文件已创建
2. ✅ Clash 订阅链接已配置
3. ✅ 环境变量已设置

## 📋 部署到老家电脑的步骤

### 1. 准备目标机器

```bash
# 检查 Docker 版本
docker --version  # 需要 20.10+
docker-compose --version  # 需要 2.0+

# 如果未安装，参考：https://docs.docker.com/engine/install/
```

### 2. 传输代码

**方式 A：使用 Git（推荐）**
```bash
# 在目标机器上
git clone <你的仓库地址>
cd nautilus-practice
git checkout feat/spot-futures-arbitrage  # 或当前分支
```

**方式 B：使用 rsync/scp**
```bash
# 在本地机器上
rsync -avz --exclude='.git' --exclude='data/raw' --exclude='output' \
  /home/yixian/Projects/nautilus-practice/ \
  user@remote-host:/path/to/nautilus-practice/
```

### 3. 配置环境变量

```bash
# 在目标机器上
cd nautilus-practice

# 复制 .env 文件（已包含订阅链接）
# 如果通过 Git 传输，需要手动创建 .env
cat > .env << 'ENVEOF'
CLASH_SUBSCRIPTION_URL=https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1
NAUTILUS_ENV=sandbox
LOG_LEVEL=DEBUG
TZ=UTC
ENVEOF
```

### 4. 首次构建和测试

```bash
# 构建镜像（首次需要 5-10 分钟）
docker-compose build

# 启动服务（前台运行，方便观察）
docker-compose up

# 观察日志，确认：
# 1. Mihomo 代理启动成功
# 2. 代理连通性检查通过
# 3. 配置验证通过
# 4. 回测开始执行
```

### 5. 验证部署

```bash
# 检查容器状态
docker-compose ps

# 查看 Mihomo 日志
docker-compose logs mihomo

# 查看主应用日志
docker-compose logs nautilus-keltner

# 检查回测结果
ls -lh output/backtest/result/
```

### 6. 后台运行（可选）

```bash
# 停止前台运行
Ctrl+C

# 后台启动
docker-compose up -d

# 查看日志
docker-compose logs -f nautilus-keltner
```

## 🔍 故障排查

### 问题 1：代理连接失败

**症状**：日志显示 "代理未就绪，等待 5 秒..."

**解决**：
```bash
# 1. 检查 Mihomo 容器状态
docker-compose ps mihomo

# 2. 查看 Mihomo 日志
docker-compose logs mihomo

# 3. 手动测试订阅链接
curl -I "https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1"

# 4. 如果订阅失效，更新 .env 中的 CLASH_SUBSCRIPTION_URL
```

### 问题 2：数据缺失

**症状**：回测报错 "No data found"

**解决**：
```bash
# 检查数据目录
ls -lh data/raw/
ls -lh data/instrument/

# 如果缺少数据，需要先下载
# 参考 docs/FUNDING_ARBITRAGE_BACKTEST_ANALYSIS.md
```

### 问题 3：内存不足

**症状**：容器被 OOM killed

**解决**：
```bash
# 检查目标机器内存
free -h

# 如果内存不足，调整 docker-compose.yml 中的内存限制
# 将 8G 改为 4G（最小值）
```

## 📊 预期结果

- **首次构建时间**：5-10 分钟
- **镜像大小**：约 800MB-1GB
- **启动时间**：1-2 分钟
- **回测时间**：取决于数据量（预计 5-20 分钟）

## 🎯 下一步

部署成功后，可以：

1. **切换到 live 模式**：
   ```bash
   # 修改 .env
   NAUTILUS_ENV=live
   
   # 重启服务
   docker-compose down
   docker-compose up -d
   ```

2. **定期执行回测**：
   ```bash
   # 添加 cron 任务
   0 2 * * * cd /path/to/nautilus-practice && docker-compose up
   ```

3. **监控和告警**：
   - 参考 `docker/README.md` 的监控章节

## 📞 支持

- 详细文档：`docker/README.md`
- 技术规格：`.omc/autopilot/spec.md`
- 问题反馈：GitHub Issues
