# Nautilus Practice 文档中心

欢迎来到 Nautilus Practice 量化交易项目文档中心。

## 📚 文档导航

### 快速开始
- [部署指南](deployment/deployment-guide.md) - 环境配置、数据准备、启动流程

### 策略文档
- [Keltner RS Breakout 策略](guides/keltner-rs-breakout.md) - 中频趋势跟踪策略
- [Dual Thrust 策略](guides/dual-thrust.md) - 经典日内突破策略

### API 文档
- [Strategy 模块 API](api/strategy-api.md) - 策略基类和配置
- [Utils 模块 API](api/utils-api.md) - 工具函数和数据管理

### 其他文档
- [OKX Testnet 配置](OKX_TESTNET_SETUP.md)
- [同步指南](SYNC_GUIDE.md)

## 📖 文档结构

```
docs/
├── README.md                    # 文档导航（本文件）
├── api/                         # API 文档
│   ├── strategy-api.md         # 策略模块 API
│   └── utils-api.md            # 工具模块 API
├── guides/                      # 使用指南
│   ├── keltner-rs-breakout.md  # Keltner RS Breakout 策略
│   └── dual-thrust.md          # Dual Thrust 策略
├── deployment/                  # 部署文档
│   └── deployment-guide.md     # 部署指南
├── analysis/                    # 分析报告
├── optimization/                # 优化文档
├── refactoring/                 # 重构文档
└── reviews/                     # 代码审查
```

## 🎯 文档使用建议

### 新手入门
1. 阅读 [部署指南](deployment/deployment-guide.md) 配置环境
2. 查看 [Keltner RS Breakout 策略](guides/keltner-rs-breakout.md) 了解策略逻辑
3. 参考 [Strategy API](api/strategy-api.md) 开发自己的策略

### 策略开发者
1. 查阅 [Strategy API](api/strategy-api.md) 了解基类接口
2. 参考现有策略文档学习最佳实践
3. 使用 [Utils API](api/utils-api.md) 中的工具函数

### 运维人员
1. 遵循 [部署指南](deployment/deployment-guide.md) 进行部署
2. 配置监控和日志系统
3. 定期检查数据完整性

## 🔄 文档更新

文档随代码同步更新，如发现文档与代码不一致，请提交 Issue。

---

**最后更新**: 2026-02-19
**版本**: v2.1
