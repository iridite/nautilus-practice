# 完整部署流程：从开发到生产

本文档描述如何将 Nautilus Keltner 策略从开发环境部署到老家电脑（生产环境）。

---

## 📋 部署流程概览

```
开发机器                          镜像仓库                      老家电脑
   │                                │                            │
   ├─ 1. 构建镜像                   │                            │
   ├─ 2. 发布到仓库 ──────────────> │                            │
   │                                │                            │
   │                                │ <──── 3. 拉取镜像 ─────────┤
   │                                │                            │
   │                                │                            ├─ 4. 启动服务
   │                                │                            ├─ 5. 验证运行
```

---

## 🚀 步骤 1：在开发机器上构建和发布镜像

### 1.1 确保代码已提交

```bash
# 检查 git 状态
git status

# 如果有未提交的更改，先提交
git add .
git commit -m "feat: update keltner strategy"
git push
```

### 1.2 发布镜像到阿里云（推荐）

```bash
# 方法 1：使用脚本（推荐）
./docker/publish-image.sh \
  -r aliyun \
  -u your-aliyun-account@example.com \
  -p your-registry-password \
  -n nautilus \
  -t v1.0.0

# 方法 2：使用环境变量
source .env.publish  # 包含你的凭证
./docker/publish-image.sh \
  -r aliyun \
  -u "$ALIYUN_USERNAME" \
  -p "$ALIYUN_PASSWORD" \
  -n "$ALIYUN_NAMESPACE" \
  -t v1.0.0
```

**输出示例**：
```
========================================
Docker 镜像发布
========================================
仓库类型: aliyun
仓库地址: registry.cn-hangzhou.aliyuncs.com
镜像名称: registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0
用户名: your-account@example.com
========================================

[1/4] 构建 Docker 镜像...
✓ 镜像构建成功

[2/4] 登录镜像仓库...
✓ 登录成功

[3/4] 推送镜像到仓库...
✓ 镜像推送成功

[4/4] 推送 latest 标签...
✓ latest 标签推送成功

========================================
发布完成！
========================================
镜像地址: registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0
```

### 1.3 记录镜像地址

将镜像地址保存下来，后续在老家电脑上使用：
```
registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0
```

---

## 📦 步骤 2：在老家电脑上部署

### 2.1 准备部署目录

```bash
# SSH 登录到老家电脑
ssh user@your-home-pc

# 创建部署目录
mkdir -p ~/nautilus-practice
cd ~/nautilus-practice
```

### 2.2 准备必需文件

你需要从开发机器复制以下文件到老家电脑：

```bash
# 在开发机器上执行
rsync -avz \
  --include='docker/' \
  --include='docker/mihomo-config.yaml.template' \
  --include='docker-compose.prod.yml' \
  --include='config/' \
  --include='data/instrument/' \
  --exclude='*' \
  ./ user@your-home-pc:~/nautilus-practice/
```

或者手动复制这些文件：
- `docker/mihomo-config.yaml.template`
- `docker-compose.prod.yml`
- `config/` 目录（所有配置文件）
- `data/instrument/` 目录（交易对配置）

### 2.3 创建 .env 文件

在老家电脑上创建 `.env` 文件：

```bash
cat > .env << 'EOF'
# 代理订阅链接
CLASH_SUBSCRIPTION_URL=https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1

# Docker 镜像地址（使用你发布的镜像）
DOCKER_IMAGE=registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0

# 运行环境
NAUTILUS_ENV=sandbox

# 日志级别
LOG_LEVEL=INFO

# 时区
TZ=UTC
EOF
```

### 2.4 创建必需目录

```bash
mkdir -p data output logs
```

### 2.5 启动服务

```bash
# 使用生产配置启动
docker compose -f docker-compose.prod.yml up -d
```

**输出示例**：
```
[+] Running 3/3
 ✔ Network nautilus-practice_nautilus-network  Created
 ✔ Container mihomo-proxy                      Started
 ✔ Container nautilus-keltner                  Started
```

---

## ✅ 步骤 3：验证部署

### 3.1 检查容器状态

```bash
docker compose -f docker-compose.prod.yml ps
```

**预期输出**：
```
NAME                 STATUS              PORTS
mihomo-proxy         Up (healthy)        7890, 7891, 9090
nautilus-keltner     Up                  -
```

### 3.2 查看日志

```bash
# 查看主应用日志
docker compose -f docker-compose.prod.yml logs -f nautilus-keltner

# 查看代理日志
docker compose -f docker-compose.prod.yml logs mihomo
```

**成功标志**：
```
✓ Mihomo 代理已就绪
✓ 配置验证通过
开始执行回测...
```

### 3.3 检查输出结果

```bash
# 等待回测完成（通常需要几分钟）
sleep 300

# 查看输出文件
ls -lh output/backtest/result/

# 查看最新结果
cat output/backtest/result/backtest_result_*.json | jq .
```

---

## 🔄 步骤 4：更新部署

当你在开发机器上更新了代码，需要重新部署：

### 4.1 在开发机器上发布新版本

```bash
# 发布新版本
./docker/publish-image.sh \
  -r aliyun \
  -u "$ALIYUN_USERNAME" \
  -p "$ALIYUN_PASSWORD" \
  -n "$ALIYUN_NAMESPACE" \
  -t v1.1.0
```

### 4.2 在老家电脑上更新

```bash
# 更新 .env 文件中的镜像版本
sed -i 's/v1.0.0/v1.1.0/g' .env

# 拉取新镜像
docker compose -f docker-compose.prod.yml pull

# 重启服务
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

---

## 🔧 常用运维命令

### 查看服务状态

```bash
docker compose -f docker-compose.prod.yml ps
```

### 查看实时日志

```bash
docker compose -f docker-compose.prod.yml logs -f
```

### 重启服务

```bash
docker compose -f docker-compose.prod.yml restart
```

### 停止服务

```bash
docker compose -f docker-compose.prod.yml down
```

### 查看资源使用

```bash
docker stats
```

### 清理旧镜像

```bash
# 清理未使用的镜像
docker image prune -a

# 清理所有未使用的资源
docker system prune -a
```

---

## 📅 定时执行（可选）

### 方法 1：Cron 定时任务

```bash
# 编辑 crontab
crontab -e

# 添加定时任务（每天凌晨 2 点执行）
0 2 * * * cd ~/nautilus-practice && docker compose -f docker-compose.prod.yml up
```

### 方法 2：Systemd Timer

创建服务文件：

```bash
sudo nano /etc/systemd/system/nautilus-keltner.service
```

内容：
```ini
[Unit]
Description=Nautilus Keltner Strategy
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/home/user/nautilus-practice
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up
User=user

[Install]
WantedBy=multi-user.target
```

创建定时器：

```bash
sudo nano /etc/systemd/system/nautilus-keltner.timer
```

内容：
```ini
[Unit]
Description=Run Nautilus Keltner Strategy daily

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

启用定时器：

```bash
sudo systemctl daemon-reload
sudo systemctl enable nautilus-keltner.timer
sudo systemctl start nautilus-keltner.timer

# 查看定时器状态
sudo systemctl list-timers
```

---

## 🐛 故障排查

### 问题 1：镜像拉取失败

**症状**：
```
Error response from daemon: pull access denied
```

**解决**：
```bash
# 检查镜像地址是否正确
cat .env | grep DOCKER_IMAGE

# 手动登录镜像仓库
docker login registry.cn-hangzhou.aliyuncs.com

# 手动拉取镜像
docker pull registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0
```

### 问题 2：代理连接失败

**症状**：
```
代理未就绪，等待 5 秒...
```

**解决**：
```bash
# 检查 Mihomo 日志
docker compose -f docker-compose.prod.yml logs mihomo

# 测试订阅链接
curl -I "https://rkuoe.no-mad-world.club/link/G1qWf3dIQkoWLjF3?clash=3&extend=1"

# 重启代理服务
docker compose -f docker-compose.prod.yml restart mihomo
```

### 问题 3：配置文件缺失

**症状**：
```
FileNotFoundError: config/strategies/keltner.yaml
```

**解决**：
```bash
# 从开发机器同步配置文件
rsync -avz config/ user@home-pc:~/nautilus-practice/config/
```

### 问题 4：数据文件缺失

**症状**：
```
FileNotFoundError: data/instrument/BINANCE/...
```

**解决**：
```bash
# 从开发机器同步数据文件
rsync -avz data/instrument/ user@home-pc:~/nautilus-practice/data/instrument/
```

---

## 📊 监控和告警（可选）

### 使用 Watchtower 自动更新镜像

```bash
docker run -d \
  --name watchtower \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --interval 3600 \
  nautilus-keltner
```

### 使用 Portainer 管理容器

```bash
docker run -d \
  -p 9000:9000 \
  --name portainer \
  --restart=always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v portainer_data:/data \
  portainer/portainer-ce
```

访问：`http://your-home-pc:9000`

---

## 📞 获取帮助

- 发布指南：`docker/PUBLISH_GUIDE.md`
- 快速开始：`docker/QUICK_START.md`
- 部署检查清单：`docker/DEPLOYMENT_CHECKLIST.md`
- 项目文档：`docker/README.md`

---

## 🎯 最佳实践

1. **版本管理**：
   - 使用语义化版本号（v1.0.0, v1.1.0）
   - 生产环境使用固定版本，不要用 `latest`

2. **安全性**：
   - 不要在 Git 中提交 `.env` 文件
   - 使用强密码保护镜像仓库
   - 定期更新基础镜像

3. **备份**：
   - 定期备份 `output/` 目录
   - 备份配置文件到云端

4. **监控**：
   - 定期检查容器状态
   - 监控磁盘空间使用
   - 设置日志轮转

5. **更新策略**：
   - 在测试环境验证新版本
   - 使用蓝绿部署或滚动更新
   - 保留旧版本镜像以便回滚
