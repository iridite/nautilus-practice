# 快速开始指南

## 🚀 三种部署方式

### 方式 1：完全自动化（推荐）

**适用场景**：在老家电脑上直接运行

```bash
# 1. 克隆代码
git clone <仓库地址>
cd nautilus-practice

# 2. 一键部署（完全自动，无需交互）
./docker/quick-deploy.sh
```

**特点**：
- ✅ 自动创建 .env 文件（已包含订阅链接）
- ✅ 自动构建 Docker 镜像
- ✅ 自动启动服务（后台模式）
- ✅ 无需任何手动配置

---

### 方式 2：远程部署（从本地推送）

**适用场景**：从你的开发机器部署到老家电脑

```bash
# 在本地机器运行
./docker/remote-deploy.sh
```

**交互提示**：
```
远程机器 IP 或域名: 192.168.1.100
远程机器用户名 [默认: root]: your-user
远程部署路径 [默认: ~/nautilus-practice]: /opt/nautilus
确认部署? [y/N]: y
```

**特点**：
- ✅ 自动通过 SSH 连接远程机器
- ✅ 自动传输代码（rsync）
- ✅ 自动远程构建和启动
- ✅ 自动验证部署状态

**前置要求**：
- 配置 SSH 密钥认证（避免输入密码）
- 远程机器已安装 Docker

---

### 方式 3：交互式部署（推荐首次部署）

**适用场景**：首次部署，需要检查环境和观察日志

```bash
./docker/deploy.sh
```

**自动检查**：
- ✅ Docker 环境（版本、安装状态）
- ✅ 硬件资源（CPU、内存、磁盘）
- ✅ 环境变量配置
- ✅ 数据文件完整性

**交互选择**：
```
选择启动模式:
  1) 前台运行（推荐首次部署，方便观察日志）
  2) 后台运行（适合长期运行）
```

---

## 📋 部署后验证

### 检查容器状态
```bash
docker-compose ps
```

**预期输出**：
```
NAME                    STATUS              PORTS
mihomo                  Up (healthy)        7890, 7891, 9090
nautilus-keltner        Up                  -
```

### 查看日志
```bash
# 查看主应用日志
docker-compose logs -f nautilus-keltner

# 查看代理日志
docker-compose logs mihomo
```

**成功标志**：
```
✓ Mihomo 代理已就绪
✓ 配置验证通过
开始执行回测...
```

### 查看回测结果
```bash
ls -lh output/backtest/result/
```

---

## 🔧 常用命令

### 停止服务
```bash
docker-compose down
```

### 重启服务
```bash
docker-compose restart
```

### 查看资源使用
```bash
docker stats
```

### 清理所有数据（谨慎使用）
```bash
docker-compose down -v
```

---

## 🐛 故障排查

### 问题 1：代理连接失败

**症状**：
```
代理未就绪，等待 5 秒...
```

**解决**：
```bash
# 检查 Mihomo 日志
docker-compose logs mihomo

# 手动测试订阅链接
curl -I "https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1"
```

### 问题 2：构建失败

**症状**：
```
ERROR: failed to solve: process "/bin/sh -c ..." did not complete successfully
```

**解决**：
```bash
# 清理 Docker 缓存
docker system prune -a

# 重新构建
docker-compose build --no-cache
```

### 问题 3：内存不足

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

---

## 📞 获取帮助

- 详细文档：`docker/README.md`
- 部署检查清单：`docker/DEPLOYMENT_CHECKLIST.md`
- 技术规格：`.omc/autopilot/spec.md`

---

## 🎯 下一步

部署成功后：

1. **切换到 live 模式**：
   ```bash
   # 编辑 .env
   NAUTILUS_ENV=live
   
   # 重启服务
   docker-compose down && docker-compose up -d
   ```

2. **定期执行回测**：
   ```bash
   # 添加 cron 任务（每天凌晨 2 点）
   0 2 * * * cd /path/to/nautilus-practice && docker-compose up
   ```

3. **监控服务状态**：
   ```bash
   # 查看容器健康状态
   docker-compose ps
   
   # 查看资源使用
   docker stats
   ```
