# Docker 部署检查清单

本文档记录了 Docker 部署前的所有检查项和潜在问题。

## 检查状态

**最后检查时间**: 2026-03-02
**当前分支**: `fix/entrypoint-universe-generation`
**检查结果**: ✅ 所有检查通过

---

## 1. 基础配置检查

### ✅ Dockerfile
- [x] 正确的 uv PATH 配置 (`/root/.local/bin`)
- [x] 所有必需目录已复制 (strategy, backtest, core, utils, config, scripts, cli, sandbox)
- [x] 数据目录结构已创建 (data/instrument, data/top, data/universe, data/raw)
- [x] entrypoint 脚本已复制并设置执行权限
- [x] 创建非 root 用户 (nautilus)
- [x] 正确设置目录权限

### ✅ docker-compose.prod.yml
- [x] OKX API 环境变量配置 (OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE)
- [x] 代理配置 (HTTP_PROXY, HTTPS_PROXY)
- [x] Volume 挂载 (./data, ./output, ./logs)
- [x] Mihomo 依赖配置 (condition: service_healthy)

### ✅ entrypoint-auto.sh
- [x] 代理等待逻辑 (nc -z 检查)
- [x] 数据文件检查
- [x] Universe 生成逻辑
- [x] 配置文件验证
- [x] 启动命令 (exec python main.py)

---

## 2. 配置文件检查

### ✅ config/active.yaml
- [x] 环境设置为 `sandbox`
- [x] 策略设置为 `keltner_rs_breakout`

### ✅ config/environments/sandbox.yaml
- [x] Universe 配置正确
  - `enabled: true`
  - `auto_generate: true`
  - `file: "data/universe/universe_15_W-MON.json"`
  - `strict_mode: false` (允许 fallback)
- [x] `instrument_ids` 为空或注释 (从 Universe 自动生成)
- [x] `allow_missing_instruments: true` (允许缺失 instrument json)

### ✅ config/strategies/keltner_rs_breakout.yaml
- [x] `universe_top_n: 15`
- [x] `universe_freq: W-MON`
- [x] 与 sandbox.yaml 的 Universe 配置一致

---

## 3. 代码逻辑检查

### ✅ sandbox/engine.py
- [x] `_load_universe_symbols` 方法存在
- [x] Universe period fallback 逻辑 (使用最新可用周期)
- [x] 支持从 Universe 动态加载 instruments

### ✅ sandbox/preflight.py
- [x] 环境变量检查 (OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE)
- [x] 策略模块导入检查
- [x] Instrument 文件检查 (带 `allow_missing_instruments` 支持)

---

## 4. 数据目录检查

### ✅ 本地数据目录
- [x] `data/instrument/` 存在
- [x] `data/top/` 存在且有数据 (Universe 生成需要)
- [x] `data/universe/` 存在
- [x] `data/raw/` 存在

### ✅ Docker 数据目录
- [x] Dockerfile 创建所有必需的数据目录
- [x] docker-compose.prod.yml 正确挂载 `./data:/app/data`

---

## 5. 环境变量检查

### ✅ .env 文件
- [x] 文件存在
- [x] 包含 `OKX_API_KEY`
- [x] 包含 `OKX_API_SECRET`
- [x] 包含 `OKX_API_PASSPHRASE`

### ✅ test.env
- [x] 软链接到 `.env` (用于测试网)

---

## 6. 运行时依赖检查

### ✅ pyproject.toml
- [x] `nautilus_trader` 已声明
- [x] `python-dotenv` 已声明
- [x] `pydantic` 已声明
- [x] `pandas` 已声明

---

## 7. 已修复的问题

### 问题 1: uv PATH 错误
**症状**: Docker 构建时 `uv: not found`
**原因**: Dockerfile PATH 指向 `/root/.cargo/bin` 而非 `/root/.local/bin`
**修复**: PR #68 - 修正 Dockerfile 第 17 行
**状态**: ✅ 已修复

### 问题 2: 缺失关键目录
**症状**: `ModuleNotFoundError: No module named 'cli'`
**原因**: Docker 镜像缺少 cli/, sandbox/, scripts/ 目录
**修复**: PR #69, #70 - 修改 Dockerfile 和 .dockerignore
**状态**: ✅ 已修复

### 问题 3: Universe 生成逻辑
**症状**: Sandbox 模式跳过 Universe 生成
**原因**: entrypoint-auto.sh 中有 sandbox 跳过逻辑
**修复**: PR #71 - 移除 sandbox 跳过逻辑,所有模式都尝试生成
**状态**: ✅ 已修复

### 问题 4: Universe period mismatch
**症状**: 当前周期 (2026-W10) 不存在,只有 2026-W09
**原因**: Universe 文件未及时更新
**修复**: sandbox/engine.py 添加 fallback 逻辑,使用最新可用周期
**状态**: ✅ 已修复

### 问题 5: 环境配置错误
**症状**: 启动时报错 "Environment does not have sandbox configuration"
**原因**: config/active.yaml 指向 dev 环境而非 sandbox
**修复**: 修改 active.yaml 为 `environment: sandbox`
**状态**: ✅ 已修复

---

## 8. 潜在问题和注意事项

### ⚠️ 健康检查过于简单
**问题**: docker-compose.prod.yml 中 nautilus-keltner 的健康检查只是 `python -c "import sys; sys.exit(0)"`
**影响**: 无法检测实际运行状态,容器可能已崩溃但健康检查仍通过
**建议**: 未来可以改进为检查进程状态或日志文件
**优先级**: 低 (不影响功能)

### ⚠️ 首次部署需要手动创建目录
**问题**: 部署到新服务器时,需要手动创建 `./data`, `./output`, `./logs` 目录
**影响**: 首次部署可能失败
**解决方案**: 在部署前运行 `mkdir -p data output logs`
**优先级**: 低 (文档已说明)

---

## 9. 部署步骤

### 本地测试
```bash
# 1. 运行所有检查
python /tmp/deployment_check.py
python /tmp/advanced_check.py
python /tmp/final_check.py

# 2. 本地测试 sandbox 模式
uv run python main.py sandbox

# 3. 检查日志
tail -f log/sandbox/*/runtime/*.log
```

### Docker 构建和推送
```bash
# 1. 构建镜像
docker build -t iridite/nautilus-keltner:latest .

# 2. 测试镜像
docker run --rm -it \
  -e OKX_API_KEY=$OKX_API_KEY \
  -e OKX_API_SECRET=$OKX_API_SECRET \
  -e OKX_API_PASSPHRASE=$OKX_API_PASSPHRASE \
  iridite/nautilus-keltner:latest

# 3. 推送镜像
docker push iridite/nautilus-keltner:latest
```

### 生产部署
```bash
# 1. 准备环境
mkdir -p data output logs
cp .env.example .env  # 编辑并填入真实的 API 凭证

# 2. 启动服务
docker compose -f docker-compose.prod.yml up -d

# 3. 查看日志
docker compose -f docker-compose.prod.yml logs -f nautilus-keltner

# 4. 检查状态
docker compose -f docker-compose.prod.yml ps
```

---

## 10. 故障排查

### 容器无法启动
1. 检查日志: `docker compose -f docker-compose.prod.yml logs nautilus-keltner`
2. 检查代理: `docker compose -f docker-compose.prod.yml logs mihomo`
3. 检查环境变量: `docker compose -f docker-compose.prod.yml config`

### Universe 加载失败
1. 检查 data/top 目录是否有数据
2. 检查 Universe 文件是否存在: `ls -la data/universe/`
3. 查看 sandbox 日志中的 Universe 加载信息

### API 连接失败
1. 检查 .env 文件中的 API 凭证
2. 检查代理是否正常: `curl -x http://localhost:7890 https://www.okx.com`
3. 检查 OKX 测试网状态

---

## 11. 检查脚本

所有检查脚本已保存在 `/tmp/`:
- `/tmp/deployment_check.py` - 基础配置检查
- `/tmp/advanced_check.py` - 高级逻辑检查
- `/tmp/final_check.py` - 最终部署模拟

可以随时重新运行这些脚本进行检查。

---

## 12. 相关文档

- [Git 工作流](./lessons-learned/GIT_WORKFLOW.md)
- [架构决策](./lessons-learned/ARCHITECTURE_DECISIONS.md)
- [策略调试](./lessons-learned/STRATEGY_DEBUGGING.md)
- [CLAUDE.md](../CLAUDE.md) - AI Agent 开发指南

---

**最后更新**: 2026-03-02
**维护者**: AI Agent + User
