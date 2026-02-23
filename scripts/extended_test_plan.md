# 扩展回测验证计划

## 目标
找到 PNL 最高且稳定的历史版本，总共测试 20 个 commit

## 第一批测试（进行中）- 4 个
基于回测结果时间推测的最可能版本：

1. ✓ `5db6a93` - feat(strategy): 添加了抛物线止盈 (2026-02-05 21:47) - 预期 PNL: 143.79
2. ✓ `7e24e5f` - fix: logic failure at handling exit method (2026-02-05 21:06) - 预期 PNL: 143.79
3. ✓ `79425ee` - fix: breakeven 止损 (2026-02-05 17:45) - 预期 PNL: 139.16
4. ✓ `dc1a2bb` - chore(config): bug discover and formatting (2026-02-05 17:21) - 预期 PNL: 139.16

## 第二批测试（备用）- 8 个
如果第一批结果不理想，测试这些版本：

5. `053bf5c` - feat(strategy): add Candle Quality Filter mechanism (2026-02-05 23:07)
6. `26cfc5c` - feat(strategy): [WIP] RSI 超买止盈 (2026-02-05 22:31)
7. `6b0d4d0` - feat(strategy): 实现针对开仓的币种进行 breakeven 止损的能力 (2026-02-05 17:10)
8. `dbd3968` - chore: move file (2026-02-05 17:10)
9. `f9008c9` - feat: 实现 live 实盘交易模块 (2026-02-03 22:46)
10. `5f6aaa2` - fix: 修复 P0 代码质量问题 (2026-02-03 21:58)
11. `0249135` - fix(strategy): 移除编辑工具残留标记导致的语法错误 (2026-02-03 18:06)
12. `3b8aea9` - feat(universe): 支持不同更新周期的 Universe 文件 (2026-02-03 17:56)

## 第三批测试（备用）- 8 个
如果前两批都不理想，继续测试：

13. `c0b13ff` - fix(strategy): 修复 Keltner RS Breakout 时间止损的 K 线计算逻辑 (2026-02-03 17:06)
14. `61d99ee` - fix(config): 更新 Keltner RS Breakout 配置以匹配代码实现 (2026-02-03 17:06)
15. `b6fb30d` - feat(core): 添加 Universe 文件不存在时的严格检查 (2026-02-03 16:57)
16. `8dde585` - feat(strategy): 优化 RS 因子为长短结合 (2026-02-03 13:00)
17. `52c6928` - feat(strategy): 优化止损机制提升盈亏比 (2026-02-03 12:45)
18. `b16a115` - docs(agents): 添加策略开发经验教训 (2026-02-03 12:31)
19. `1e57af5` - feat(strategy): 添加 BTC 市场状态过滤器 (2026-02-03 12:27)
20. `6178b81` - Enhance documentation and remove unnecessary files (2026-02-09 23:53)

## 验证标准
- PNL 是否与历史回测结果一致
- Sharpe Ratio 是否合理（> 1.0）
- 交易数量是否合理（1000-1500）
- 代码是否可以正常运行

## 最终目标
找到最佳版本后：
1. 添加 release tag（如 v1.0-best-backtest）
2. 开展代码修复和精简工作
3. 确保该版本作为稳定基线
