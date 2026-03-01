#!/bin/bash
# 快速参考 - 在老家电脑上运行此脚本

cat << 'EOF'
╔══════════════════════════════════════════════════════════════╗
║          Nautilus Keltner 策略 - 快速部署指南               ║
╚══════════════════════════════════════════════════════════════╝

📦 完全自动化部署（推荐）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣  克隆代码
   git clone https://github.com/iridite/nautilus-practice.git
   cd nautilus-practice
   git checkout fix/funding-arbitrage-code-review

2️⃣  一键部署（完全自动化）
   ./docker/auto-deploy.sh

   ✨ 自动完成：
   • 创建配置文件
   • 构建 Docker 镜像
   • 启动 Mihomo 代理
   • 下载市场数据（BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT）
   • 生成 Universe 文件
   • 运行 Keltner 策略回测

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 常用命令
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

查看实时日志：
   docker compose logs -f nautilus-keltner

查看服务状态：
   docker compose ps

查看回测结果：
   ls -lh output/backtest/result/
   cat output/backtest/result/backtest_result_*.json | jq .

停止服务：
   docker compose down

重启服务：
   docker compose restart

查看资源使用：
   docker stats

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 故障排查
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

代理连接失败：
   docker compose logs mihomo
   docker compose restart mihomo

数据下载失败：
   docker compose exec nautilus-keltner python scripts/download_full_year_data.py \
     --symbols BTCUSDT --start-date 2024-01-01 --end-date 2026-01-01

重新下载所有数据：
   rm -rf data/raw/*
   docker compose restart nautilus-keltner

内存不足：
   编辑 docker-compose.yml，将 memory: 8G 改为 4G

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📚 详细文档
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

完整部署指南：
   cat docker/AUTO_DEPLOY_GUIDE.md

快速开始：
   cat docker/QUICK_START.md

镜像发布指南：
   cat docker/PUBLISH_GUIDE.md

部署工作流：
   cat docker/DEPLOYMENT_WORKFLOW.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 成功标志
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

当你看到以下输出时，说明部署成功：

   ✓ Mihomo 代理已就绪
   ✓ 所有必需数据已存在
   ✓ Universe 文件已存在
   ✓ 配置验证通过
   开始执行 Sandbox 策略

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 下一步
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 等待回测完成（5-10 分钟）
2. 查看结果：ls -lh output/backtest/result/
3. 设置定时任务：crontab -e
   0 2 * * * cd /path/to/nautilus-practice && docker compose up

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF
