#!/usr/bin/env python3
"""
测试 compare_engine_performance.py 的修复是否成功
"""
import sys
from pathlib import Path

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.adapter import get_adapter

def test_config_loading():
    """测试配置加载是否正常"""
    print("测试配置加载...")

    try:
        # 使用 adapter 加载配置
        adapter = get_adapter()
        cfg = adapter.build_backtest_config()

        print(f"✅ 配置加载成功!")
        print(f"   策略名称: {cfg.strategy.name}")
        print(f"   配置类型: {type(cfg).__name__}")

        return True

    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_config_loading()
    sys.exit(0 if success else 1)
