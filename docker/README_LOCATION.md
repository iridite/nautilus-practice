# Docker 文件位置说明

## 文件整理 (2026-03-04)

所有 Docker 相关文件已统一移动到 `docker/` 目录:

- `Dockerfile` → `docker/Dockerfile`
- `docker-compose.yml` → `docker/docker-compose.yml`
- `docker-compose.prod.yml` → `docker/docker-compose.prod.yml`

## 使用方法

从项目根目录运行 Docker 命令时,需要指定文件路径:

```bash
# 构建镜像
docker build -f docker/Dockerfile -t nautilus-practice .

# 启动服务 (开发环境)
docker-compose -f docker/docker-compose.yml up -d

# 启动服务 (生产环境)
docker-compose -f docker/docker-compose.prod.yml up -d
```

或者进入 docker 目录:

```bash
cd docker

# 构建镜像
docker build -f Dockerfile -t nautilus-practice ..

# 启动服务
docker-compose up -d
```

## 相关文档

- [Docker 部署指南](README.md)
- [快速开始](QUICK_START.md)
- [部署检查清单](DEPLOYMENT_CHECKLIST.md)
