#!/bin/bash
# Docker 镜像发布脚本
# 支持多个镜像仓库：Docker Hub, 阿里云, 腾讯云, Harbor

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 默认配置
IMAGE_NAME="nautilus-keltner"
VERSION="${VERSION:-latest}"
BUILD_ARGS=""

# 打印帮助信息
print_help() {
    cat << EOF
用法: $0 [选项]

选项:
  -r, --registry REGISTRY   镜像仓库类型 (dockerhub|aliyun|tencent|harbor)
  -u, --username USERNAME   仓库用户名
  -p, --password PASSWORD   仓库密码
  -n, --namespace NAMESPACE 命名空间/组织名
  -t, --tag TAG            镜像标签 (默认: latest)
  -h, --help               显示帮助信息

示例:
  # 发布到 Docker Hub
  $0 -r dockerhub -u myuser -p mypass -n myorg -t v1.0.0

  # 发布到阿里云
  $0 -r aliyun -u myuser -p mypass -n mynamespace -t v1.0.0

  # 发布到腾讯云
  $0 -r tencent -u myuser -p mypass -n mynamespace -t v1.0.0

  # 发布到自建 Harbor
  HARBOR_URL=harbor.example.com $0 -r harbor -u admin -p password -n myproject -t v1.0.0

环境变量:
  HARBOR_URL    Harbor 仓库地址 (仅 harbor 类型需要)
  VERSION       镜像版本标签 (默认: latest)
EOF
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -u|--username)
            USERNAME="$2"
            shift 2
            ;;
        -p|--password)
            PASSWORD="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -t|--tag)
            VERSION="$2"
            shift 2
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            echo -e "${RED}错误: 未知参数 $1${NC}"
            print_help
            exit 1
            ;;
    esac
done

# 验证必需参数
if [[ -z "$REGISTRY" ]]; then
    echo -e "${RED}错误: 必须指定镜像仓库类型 (-r)${NC}"
    print_help
    exit 1
fi

if [[ -z "$USERNAME" ]] || [[ -z "$PASSWORD" ]]; then
    echo -e "${RED}错误: 必须提供用户名和密码${NC}"
    print_help
    exit 1
fi

if [[ -z "$NAMESPACE" ]]; then
    echo -e "${RED}错误: 必须指定命名空间/组织名 (-n)${NC}"
    print_help
    exit 1
fi

# 根据仓库类型设置镜像地址
case $REGISTRY in
    dockerhub)
        REGISTRY_URL="docker.io"
        FULL_IMAGE_NAME="${NAMESPACE}/${IMAGE_NAME}:${VERSION}"
        ;;
    aliyun)
        REGISTRY_URL="registry.cn-hangzhou.aliyuncs.com"
        FULL_IMAGE_NAME="${REGISTRY_URL}/${NAMESPACE}/${IMAGE_NAME}:${VERSION}"
        ;;
    tencent)
        REGISTRY_URL="ccr.ccs.tencentyun.com"
        FULL_IMAGE_NAME="${REGISTRY_URL}/${NAMESPACE}/${IMAGE_NAME}:${VERSION}"
        ;;
    harbor)
        if [[ -z "$HARBOR_URL" ]]; then
            echo -e "${RED}错误: Harbor 类型需要设置 HARBOR_URL 环境变量${NC}"
            exit 1
        fi
        REGISTRY_URL="$HARBOR_URL"
        FULL_IMAGE_NAME="${REGISTRY_URL}/${NAMESPACE}/${IMAGE_NAME}:${VERSION}"
        ;;
    *)
        echo -e "${RED}错误: 不支持的仓库类型: $REGISTRY${NC}"
        echo "支持的类型: dockerhub, aliyun, tencent, harbor"
        exit 1
        ;;
esac

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Docker 镜像发布${NC}"
echo -e "${GREEN}========================================${NC}"
echo "仓库类型: $REGISTRY"
echo "仓库地址: $REGISTRY_URL"
echo "镜像名称: $FULL_IMAGE_NAME"
echo "用户名: $USERNAME"
echo -e "${GREEN}========================================${NC}"
echo ""

# 1. 构建镜像
echo -e "${YELLOW}[1/4] 构建 Docker 镜像...${NC}"
docker build -t "$FULL_IMAGE_NAME" .

if [[ $? -ne 0 ]]; then
    echo -e "${RED}错误: 镜像构建失败${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 镜像构建成功${NC}"
echo ""

# 2. 登录镜像仓库
echo -e "${YELLOW}[2/4] 登录镜像仓库...${NC}"
echo "$PASSWORD" | docker login "$REGISTRY_URL" -u "$USERNAME" --password-stdin

if [[ $? -ne 0 ]]; then
    echo -e "${RED}错误: 登录失败${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 登录成功${NC}"
echo ""

# 3. 推送镜像
echo -e "${YELLOW}[3/4] 推送镜像到仓库...${NC}"
docker push "$FULL_IMAGE_NAME"

if [[ $? -ne 0 ]]; then
    echo -e "${RED}错误: 镜像推送失败${NC}"
    exit 1
fi
echo -e "${GREEN}✓ 镜像推送成功${NC}"
echo ""

# 4. 同时推送 latest 标签（如果版本不是 latest）
if [[ "$VERSION" != "latest" ]]; then
    echo -e "${YELLOW}[4/4] 推送 latest 标签...${NC}"
    LATEST_IMAGE_NAME="${FULL_IMAGE_NAME%:*}:latest"
    docker tag "$FULL_IMAGE_NAME" "$LATEST_IMAGE_NAME"
    docker push "$LATEST_IMAGE_NAME"

    if [[ $? -ne 0 ]]; then
        echo -e "${YELLOW}警告: latest 标签推送失败${NC}"
    else
        echo -e "${GREEN}✓ latest 标签推送成功${NC}"
    fi
    echo ""
fi

# 5. 清理本地镜像（可选）
echo -e "${YELLOW}是否清理本地镜像? [y/N]${NC}"
read -r -n 1 CLEANUP
echo ""
if [[ "$CLEANUP" =~ ^[Yy]$ ]]; then
    docker rmi "$FULL_IMAGE_NAME"
    if [[ "$VERSION" != "latest" ]]; then
        docker rmi "$LATEST_IMAGE_NAME" 2>/dev/null || true
    fi
    echo -e "${GREEN}✓ 本地镜像已清理${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}发布完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo "镜像地址: $FULL_IMAGE_NAME"
echo ""
echo "在其他机器上使用:"
echo "  docker pull $FULL_IMAGE_NAME"
echo ""
echo "或修改 docker-compose.yml:"
echo "  services:"
echo "    nautilus-keltner:"
echo "      image: $FULL_IMAGE_NAME"
echo "      # 注释掉 build 部分"
echo -e "${GREEN}========================================${NC}"
