# Docker 镜像发布指南

## 📦 支持的镜像仓库

- **Docker Hub**：公共/私有镜像仓库
- **阿里云容器镜像服务**：国内访问速度快
- **腾讯云容器镜像服务**：国内访问速度快
- **Harbor**：自建私有仓库

---

## 🚀 快速开始

### 1. 赋予执行权限

```bash
chmod +x docker/publish-image.sh
```

### 2. 发布到 Docker Hub

```bash
./docker/publish-image.sh \
  -r dockerhub \
  -u your-dockerhub-username \
  -p your-dockerhub-password \
  -n your-organization \
  -t v1.0.0
```

**示例**：
```bash
./docker/publish-image.sh \
  -r dockerhub \
  -u iridite \
  -p dckr_pat_xxxxxxxxxxxxx \
  -n iridite \
  -t v1.0.0
```

**结果**：
- 镜像地址：`iridite/nautilus-keltner:v1.0.0`
- Latest 标签：`iridite/nautilus-keltner:latest`

---

### 3. 发布到阿里云（推荐国内使用）

#### 3.1 创建阿里云容器镜像服务

1. 访问 [阿里云容器镜像服务](https://cr.console.aliyun.com/)
2. 创建命名空间（如 `nautilus`）
3. 获取访问凭证：
   - 用户名：阿里云账号
   - 密码：在"访问凭证"页面设置固定密码

#### 3.2 发布镜像

```bash
./docker/publish-image.sh \
  -r aliyun \
  -u your-aliyun-account \
  -p your-registry-password \
  -n nautilus \
  -t v1.0.0
```

**示例**：
```bash
./docker/publish-image.sh \
  -r aliyun \
  -u myaccount@example.com \
  -p MyPassword123 \
  -n nautilus \
  -t v1.0.0
```

**结果**：
- 镜像地址：`registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0`

---

### 4. 发布到腾讯云

#### 4.1 创建腾讯云容器镜像服务

1. 访问 [腾讯云容器镜像服务](https://console.cloud.tencent.com/tcr)
2. 创建命名空间（如 `nautilus`）
3. 获取访问凭证

#### 4.2 发布镜像

```bash
./docker/publish-image.sh \
  -r tencent \
  -u your-tencent-account \
  -p your-registry-password \
  -n nautilus \
  -t v1.0.0
```

**结果**：
- 镜像地址：`ccr.ccs.tencentyun.com/nautilus/nautilus-keltner:v1.0.0`

---

### 5. 发布到自建 Harbor

```bash
HARBOR_URL=harbor.example.com ./docker/publish-image.sh \
  -r harbor \
  -u admin \
  -p Harbor12345 \
  -n myproject \
  -t v1.0.0
```

**结果**：
- 镜像地址：`harbor.example.com/myproject/nautilus-keltner:v1.0.0`

---

## 📥 在老家电脑上使用发布的镜像

### 方法 1：修改 docker-compose.yml

编辑 `docker-compose.yml`：

```yaml
services:
  nautilus-keltner:
    # 注释掉 build 部分
    # build:
    #   context: .
    #   dockerfile: Dockerfile

    # 使用发布的镜像
    image: registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0

    # 其他配置保持不变
    container_name: nautilus-keltner
    depends_on:
      mihomo:
        condition: service_healthy
    # ...
```

### 方法 2：直接拉取镜像

```bash
# 拉取镜像
docker pull registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0

# 运行容器
docker run -d \
  --name nautilus-keltner \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/output:/app/output \
  -v $(pwd)/config:/app/config:ro \
  -e NAUTILUS_ENV=sandbox \
  registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:v1.0.0
```

---

## 🔐 安全最佳实践

### 1. 使用环境变量存储凭证

创建 `.env.publish` 文件（不要提交到 Git）：

```bash
# Docker Hub
DOCKERHUB_USERNAME=your-username
DOCKERHUB_PASSWORD=your-password
DOCKERHUB_NAMESPACE=your-org

# 阿里云
ALIYUN_USERNAME=your-account@example.com
ALIYUN_PASSWORD=your-password
ALIYUN_NAMESPACE=nautilus

# 腾讯云
TENCENT_USERNAME=your-account
TENCENT_PASSWORD=your-password
TENCENT_NAMESPACE=nautilus

# Harbor
HARBOR_URL=harbor.example.com
HARBOR_USERNAME=admin
HARBOR_PASSWORD=your-password
HARBOR_NAMESPACE=myproject
```

使用环境变量：

```bash
source .env.publish

./docker/publish-image.sh \
  -r aliyun \
  -u "$ALIYUN_USERNAME" \
  -p "$ALIYUN_PASSWORD" \
  -n "$ALIYUN_NAMESPACE" \
  -t v1.0.0
```

### 2. 添加到 .gitignore

```bash
echo ".env.publish" >> .gitignore
```

---

## 🏷️ 版本标签策略

### 语义化版本

```bash
# 主版本更新（不兼容的 API 变更）
./docker/publish-image.sh -r aliyun -u ... -n ... -t v2.0.0

# 次版本更新（新功能，向后兼容）
./docker/publish-image.sh -r aliyun -u ... -n ... -t v1.1.0

# 修订版本（Bug 修复）
./docker/publish-image.sh -r aliyun -u ... -n ... -t v1.0.1
```

### 环境标签

```bash
# 开发环境
./docker/publish-image.sh -r aliyun -u ... -n ... -t dev

# 测试环境
./docker/publish-image.sh -r aliyun -u ... -n ... -t staging

# 生产环境
./docker/publish-image.sh -r aliyun -u ... -n ... -t prod
```

### Git 提交标签

```bash
# 使用 Git commit hash
GIT_HASH=$(git rev-parse --short HEAD)
./docker/publish-image.sh -r aliyun -u ... -n ... -t "$GIT_HASH"
```

---

## 🔄 自动化发布（CI/CD）

### GitHub Actions 示例

创建 `.github/workflows/publish-docker.yml`：

```yaml
name: Publish Docker Image

on:
  push:
    tags:
      - 'v*'

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Login to Aliyun Registry
        uses: docker/login-action@v2
        with:
          registry: registry.cn-hangzhou.aliyuncs.com
          username: ${{ secrets.ALIYUN_USERNAME }}
          password: ${{ secrets.ALIYUN_PASSWORD }}

      - name: Extract version
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/}" >> $GITHUB_OUTPUT

      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: |
            registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:${{ steps.version.outputs.VERSION }}
            registry.cn-hangzhou.aliyuncs.com/nautilus/nautilus-keltner:latest
```

---

## 📊 镜像大小优化

当前镜像大小约 **800MB**，已经通过以下方式优化：

1. ✅ 多阶段构建（builder + runtime）
2. ✅ 使用 `python:3.12-slim` 基础镜像
3. ✅ 清理 apt 缓存
4. ✅ 使用 `.dockerignore` 排除不必要文件

进一步优化建议：

```dockerfile
# 使用 alpine 基础镜像（更小，但可能有兼容性问题）
FROM python:3.12-alpine AS runtime

# 或使用 distroless 镜像（最小化攻击面）
FROM gcr.io/distroless/python3-debian12
```

---

## 🐛 故障排查

### 问题 1：登录失败

**症状**：
```
Error response from daemon: login attempt to ... failed with status: 401 Unauthorized
```

**解决**：
- 检查用户名和密码是否正确
- 阿里云：确认已设置固定密码（不是登录密码）
- Docker Hub：使用 Access Token 而非密码

### 问题 2：推送失败（权限不足）

**症状**：
```
denied: requested access to the resource is denied
```

**解决**：
- 确认命名空间已创建
- 检查账号是否有推送权限
- Harbor：确认项目存在且用户有权限

### 问题 3：镜像拉取慢

**解决**：
- 国内用户使用阿里云或腾讯云镜像仓库
- 配置 Docker 镜像加速器

---

## 📞 获取帮助

- 脚本帮助：`./docker/publish-image.sh --help`
- 项目文档：`docker/README.md`
- 部署指南：`docker/QUICK_START.md`
