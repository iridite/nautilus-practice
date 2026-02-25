# 数据下载优化

## 概述

项目已实现并发下载优化，大幅提升数据获取速度。通过多线程并发请求交易所 API，可以将下载时间缩短 5-10 倍。

## 功能特性

### 并发下载支持

- **OHLCV 数据**: 支持多线程并发下载历史 K 线数据
- **OI/Funding Rate**: 支持并发获取持仓量和资金费率数据
- **智能缓存**: 自动跳过已下载的数据文件
- **进度显示**: 实时显示下载进度和状态

### 性能提升

| 场景 | 串行下载 | 并发下载 (10 workers) | 提升倍数 |
|------|---------|---------------------|---------|
| 265 个交易对 | ~40 分钟 | ~4-8 分钟 | 5-10x |
| 50 个交易对 | ~8 分钟 | ~1-2 分钟 | 4-8x |

## 配置方法

### 环境变量配置

通过设置 `NAUTILUS_MAX_WORKERS` 环境变量控制并发数量：

```bash
# 临时设置（当前会话）
export NAUTILUS_MAX_WORKERS=15

# 运行回测
uv run main.py backtest --type high
```

```bash
# 永久设置（添加到 ~/.bashrc 或 ~/.zshrc）
echo 'export NAUTILUS_MAX_WORKERS=15' >> ~/.bashrc
source ~/.bashrc
```

### 推荐配置

| 网络环境 | 推荐值 | 说明 |
|---------|-------|------|
| 国内网络 | 5-8 | 避免触发 API 限流 |
| 海外网络 | 10-15 | 可以更激进 |
| VPN/代理 | 8-12 | 根据代理稳定性调整 |
| 默认值 | 10 | 适合大多数场景 |

## 使用示例

### 基本使用

```bash
# 使用默认并发数（10）
uv run main.py backtest --type high

# 使用自定义并发数
NAUTILUS_MAX_WORKERS=15 uv run main.py backtest --type high
```

### 下载特定数据

```bash
# 下载 Top 交易对数据（并发）
NAUTILUS_MAX_WORKERS=12 uv run scripts/prepare_top_data.py

# 强制重新下载（覆盖已有数据）
NAUTILUS_MAX_WORKERS=12 uv run scripts/prepare_top_data.py --force
```

## 注意事项

### API 限流

- **Binance**: 每分钟 1200 次请求，每秒 20 次请求
- **OKX**: 每 2 秒 20 次请求
- 过高的并发数可能触发限流，导致下载失败
- 建议从默认值开始，逐步调整

### 网络稳定性

- 并发下载对网络稳定性要求较高
- 如果频繁出现连接错误，降低并发数
- 使用稳定的网络环境（有线 > WiFi）

### 系统资源

- 每个 worker 会创建独立的 exchange 实例
- 内存占用: ~50-100MB per worker
- 建议并发数不超过 20

## 故障排查

### 下载速度没有提升

1. 检查是否大部分数据已缓存（跳过下载）
2. 检查网络带宽是否成为瓶颈
3. 尝试增加并发数

### 频繁出现连接错误

1. 降低并发数（如 5-8）
2. 检查网络连接稳定性
3. 检查是否触发 API 限流

### 内存占用过高

1. 降低并发数
2. 检查是否有内存泄漏

## 技术实现

### 架构设计

```
batch_fetch_ohlcv()
  └─> ThreadPoolExecutor(max_workers)
       ├─> _fetch_single_symbol() [Thread 1]
       ├─> _fetch_single_symbol() [Thread 2]
       ├─> ...
       └─> _fetch_single_symbol() [Thread N]
```

### 线程安全

- 每个线程创建独立的 `ccxt.Exchange` 实例
- 避免共享状态，确保线程安全
- 使用 `as_completed()` 处理异步结果

### 错误处理

- 单个交易对失败不影响其他下载
- 自动重试机制（在 `retry_fetch` 中实现）
- 详细的错误日志记录

## 相关文件

- `utils/data_management/data_retrieval.py`: 核心实现
- `utils/data_management/data_manager.py`: 管理接口
- `scripts/prepare_top_data.py`: 数据准备脚本

## 更新日志

- **2025-02-24**: 初始实现并发下载功能
  - 添加 `ThreadPoolExecutor` 支持
  - 添加 `NAUTILUS_MAX_WORKERS` 环境变量
  - 优化进度显示