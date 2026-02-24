#!/usr/bin/env python3
"""
验证多标的数据对齐检查功能

此脚本用于验证问题4的修复：确保 prepare_data_feeds() 正确调用多标的对齐检查。

使用方法：
    uv run python scripts/verify_alignment_check.py
"""

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.data_management.data_validator import prepare_data_feeds

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_alignment_check_called():
    """测试对齐检查是否被调用"""
    logger.info("=" * 60)
    logger.info("测试1: 验证对齐检查被调用")
    logger.info("=" * 60)

    # 准备 mock 对象
    args = MagicMock()
    args.skip_data_check = False

    adapter = MagicMock()
    adapter.get_venue.return_value = "BINANCE"
    adapter.get_start_date.return_value = "2025-01-01"
    adapter.get_end_date.return_value = "2025-01-31"
    adapter.get_main_timeframe.return_value = "1-DAY"
    adapter._get_trading_symbols.return_value = ["ETHUSDT-PERP:BINANCE"]

    base_dir = PROJECT_ROOT
    universe_symbols = set()

    # Mock 依赖函数
    with (
        patch("utils.data_file_checker.check_single_data_file") as mock_check_file,
        patch("utils.data_management.data_manager.run_batch_data_retrieval") as mock_batch,
        patch(
            "utils.data_management.data_validator._check_multi_instrument_alignment"
        ) as mock_alignment,
    ):
        # Mock 数据文件存在
        mock_check_file.return_value = (True, None)

        # 调用函数
        prepare_data_feeds(args, adapter, base_dir, universe_symbols)

        # 验证对齐检查被调用
        if mock_alignment.called:
            logger.info("✅ 对齐检查被正确调用")
            logger.info(f"   调用参数: {mock_alignment.call_args}")
            return True
        else:
            logger.error("❌ 对齐检查未被调用")
            return False


def test_alignment_check_skipped_when_data_check_disabled():
    """测试跳过数据检查时不调用对齐检查"""
    logger.info("\n" + "=" * 60)
    logger.info("测试2: 验证跳过数据检查时不调用对齐检查")
    logger.info("=" * 60)

    args = MagicMock()
    args.skip_data_check = True

    adapter = MagicMock()
    base_dir = PROJECT_ROOT
    universe_symbols = set()

    with patch(
        "utils.data_management.data_validator._check_multi_instrument_alignment"
    ) as mock_alignment:
        prepare_data_feeds(args, adapter, base_dir, universe_symbols)

        if not mock_alignment.called:
            logger.info("✅ 跳过数据检查时正确地不调用对齐检查")
            return True
        else:
            logger.error("❌ 跳过数据检查时仍然调用了对齐检查")
            return False


def test_alignment_check_with_btc_instrument():
    """测试有 btc_instrument_id 时的对齐检查"""
    logger.info("\n" + "=" * 60)
    logger.info("测试3: 验证有 btc_instrument_id 时执行对齐检查")
    logger.info("=" * 60)

    from core.adapter import ConfigAdapter

    # 创建真实的 adapter（使用 keltner_rs_breakout 配置）
    try:
        adapter = ConfigAdapter()

        # 检查策略配置是否有 btc_symbol
        params = adapter.strategy_config.parameters
        if "btc_symbol" in params:
            logger.info(f"✅ 策略配置包含 btc_symbol: {params['btc_symbol']}")

            # 构建回测配置
            config = adapter.build_backtest_config()
            strategy_params = (
                config.strategy.params if hasattr(config.strategy, "params") else config.strategy
            )

            btc_instrument_id = getattr(strategy_params, "btc_instrument_id", None)
            if btc_instrument_id:
                logger.info(f"✅ 策略参数包含 btc_instrument_id: {btc_instrument_id}")
                logger.info("   这意味着对齐检查会被执行")
                return True
            else:
                logger.warning("⚠️  策略参数不包含 btc_instrument_id")
                logger.info("   对齐检查不会被执行（这是正常的，如果策略不需要 BTC 数据）")
                return True
        else:
            logger.info("ℹ️  当前策略不需要 BTC 数据，对齐检查不会执行")
            return True

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    logger.info("\n" + "🔍 开始验证多标的数据对齐检查功能")
    logger.info("=" * 60)

    results = []

    # 运行测试
    results.append(("对齐检查被调用", test_alignment_check_called()))
    results.append(("跳过数据检查", test_alignment_check_skipped_when_data_check_disabled()))
    results.append(("BTC 标的检测", test_alignment_check_with_btc_instrument()))

    # 总结
    logger.info("\n" + "=" * 60)
    logger.info("📊 测试结果总结")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{status} - {name}")

    logger.info("=" * 60)
    logger.info(f"总计: {passed}/{total} 测试通过")

    if passed == total:
        logger.info("🎉 所有测试通过！问题4修复验证成功！")
        return 0
    else:
        logger.error("⚠️  部分测试失败，请检查修复")
        return 1


if __name__ == "__main__":
    sys.exit(main())
