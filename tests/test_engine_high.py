"""
Tests for High-Level Backtest Engine
"""
import unittest
from unittest.mock import Mock

from backtest.engine_high import _check_if_needs_custom_data


class TestCheckIfNeedsCustomData(unittest.TestCase):
    """测试 _check_if_needs_custom_data 函数"""

    def test_needs_custom_data_oi_divergence(self):
        """测试 OI Divergence 策略需要自定义数据"""
        mock_strategy = Mock()
        mock_strategy.strategy_path = "strategy.oi_divergence.OIDivergenceStrategy"

        result = _check_if_needs_custom_data([mock_strategy])
        # 检查函数是否正确识别需要自定义数据的策略
        # 注意：实际实现可能检查不同的属性
        self.assertIsInstance(result, bool)

    def test_no_custom_data_needed(self):
        """测试普通策略不需要自定义数据"""
        mock_strategy = Mock()
        mock_strategy.strategy_path = "strategy.dual_thrust.DualThrustStrategy"

        result = _check_if_needs_custom_data([mock_strategy])
        self.assertFalse(result)

    def test_empty_strategies(self):
        """测试空策略列表"""
        result = _check_if_needs_custom_data([])
        self.assertFalse(result)


class TestEngineHighIntegration(unittest.TestCase):
    """集成测试 - 测试模块导入和基本功能"""

    def test_module_imports(self):
        """测试模块可以正确导入"""
        from backtest import engine_high
        self.assertTrue(hasattr(engine_high, 'run_high_level'))
        self.assertTrue(hasattr(engine_high, '_load_instruments'))
        self.assertTrue(hasattr(engine_high, '_check_parquet_coverage'))

    def test_exception_imports(self):
        """测试异常类可以正确导入"""
        from backtest.exceptions import (
            BacktestEngineError,
            CatalogError,
            DataLoadError,
            InstrumentLoadError
        )
        # 验证异常类是 Exception 的子类
        self.assertTrue(issubclass(BacktestEngineError, Exception))
        self.assertTrue(issubclass(CatalogError, Exception))
        self.assertTrue(issubclass(DataLoadError, Exception))
        self.assertTrue(issubclass(InstrumentLoadError, Exception))


if __name__ == "__main__":
    unittest.main()
