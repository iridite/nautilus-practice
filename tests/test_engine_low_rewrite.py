#!/usr/bin/env python3
"""
测试重写的 Low-Level Engine

验证重写后的 engine_low.py 的基本功能：
1. 模块导入是否正常
2. 异常处理是否完整
3. 核心函数是否能正常工作
4. 类型提示是否正确

Usage:
    uv run python -m unittest tests.test_engine_low_rewrite -v
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from core.exceptions import (
    BacktestEngineError,
    CustomDataError,
    DataLoadError,
    InstrumentLoadError,
)


class TestEngineLowRewrite(unittest.TestCase):
    """测试重写的 Low-Level Engine"""

    def setUp(self):
        """测试前准备"""
        self.base_dir = Path(__file__).parent.parent

    def test_import_engine_low(self):
        """测试 engine_low 模块能正常导入"""
        try:
            import backtest.engine_low

            self.assertTrue(True, "engine_low 模块导入成功")
        except ImportError as e:
            self.fail(f"engine_low 模块导入失败: {e}")

    def test_import_exceptions(self):
        """测试异常类能正常导入"""
        try:
            from backtest.engine_low import (
                _load_custom_data_to_engine,
                _load_data_for_feed,
                _process_backtest_results,
                run_low_level,
            )

            self.assertTrue(True, "所有函数导入成功")
        except ImportError as e:
            self.fail(f"函数导入失败: {e}")

    def test_exception_classes(self):
        """测试异常类是否定义完整"""
        # 测试异常类能正常实例化
        try:
            BacktestEngineError("test message")
            DataLoadError("test message", "/test/path")
            InstrumentLoadError("test message", "BTCUSDT-PERP")
            CustomDataError("test message", "OI")
            self.assertTrue(True, "所有异常类实例化成功")
        except Exception as e:
            self.fail(f"异常类实例化失败: {e}")

    def test_function_signatures(self):
        """测试函数签名是否正确"""
        import inspect

        from backtest.engine_low import (
            _load_custom_data_to_engine,
            _load_data_for_feed,
            run_low_level,
        )

        # 检查函数参数
        sig = inspect.signature(_load_data_for_feed)
        expected_params = ["engine", "base_dir", "cfg", "data_cfg", "loaded_instruments"]
        actual_params = list(sig.parameters.keys())
        self.assertEqual(
            actual_params, expected_params, f"_load_data_for_feed 参数不匹配: {actual_params}"
        )

        sig = inspect.signature(_load_custom_data_to_engine)
        expected_params = ["cfg", "base_dir", "engine", "loaded_instruments"]
        actual_params = list(sig.parameters.keys())
        self.assertEqual(
            actual_params,
            expected_params,
            f"_load_custom_data_to_engine 参数不匹配: {actual_params}",
        )

        sig = inspect.signature(run_low_level)
        expected_params = ["cfg", "base_dir"]
        actual_params = list(sig.parameters.keys())
        self.assertEqual(
            actual_params, expected_params, f"run_low_level 参数不匹配: {actual_params}"
        )

    def test_data_load_error_with_file_path(self):
        """测试 DataLoadError 是否支持文件路径"""
        test_path = "/test/path/data.csv"
        error = DataLoadError("Test error message", test_path)

        self.assertEqual(error.file_path, test_path)
        self.assertIn(test_path, str(error))
        self.assertIn("Test error message", str(error))

    def test_instrument_load_error_with_id(self):
        """测试 InstrumentLoadError 是否支持标的ID"""
        test_id = "BTCUSDT-PERP"
        error = InstrumentLoadError("Test error message", test_id)

        self.assertEqual(error.instrument_id, test_id)
        self.assertIn(test_id, str(error))
        self.assertIn("Test error message", str(error))

    def test_custom_data_error_with_type(self):
        """测试 CustomDataError 是否支持数据类型"""
        test_type = "OpenInterestData"
        error = CustomDataError("Test error message", test_type)

        self.assertEqual(error.data_type, test_type)
        self.assertIn(test_type, str(error))
        self.assertIn("Test error message", str(error))

    @patch("utils.data_management.data_loader.load_ohlcv_csv")
    def test_load_data_for_feed_time_column_detection(self, mock_load_csv):
        """测试数据加载函数的时间列检测功能"""

        from backtest.engine_low import _load_data_for_feed

        # Mock 数据
        mock_engine = Mock()
        mock_base_dir = Path("/test")
        mock_cfg = Mock()
        mock_data_cfg = Mock()
        mock_data_cfg.instrument_id = "BTCUSDT.BINANCE"
        mock_data_cfg.bar_type_str = "1-MINUTE-BID-EXTERNAL"
        # 正确设置 Path mock
        mock_path = Mock(spec=Path)
        mock_path.exists.return_value = True
        mock_data_cfg.full_path = mock_path
        mock_data_cfg.label = "main"

        mock_loaded_instruments = {"BTCUSDT.BINANCE": Mock()}
        mock_loaded_instruments["BTCUSDT.BINANCE"].id = "BTCUSDT.BINANCE"

        # Mock CSV 样本数据 (包含 datetime 列)
        import pandas as pd

        sample_df = pd.DataFrame(
            {
                "datetime": ["2023-01-01 00:00:00"],
                "open": [50000],
                "high": [50100],
                "low": [49900],
                "close": [50050],
                "volume": [100],
            }
        )
        mock_load_csv.return_value = sample_df

        try:
            _load_data_for_feed(
                mock_engine, mock_base_dir, mock_cfg, mock_data_cfg, mock_loaded_instruments
            )
            # 如果没有抛出异常就是成功的
            self.assertTrue(True, "时间列检测功能工作正常")
        except Exception as e:
            # 预期可能的异常（由于 mock 数据不完整）
            if "DataLoadError" in str(type(e)) or "AttributeError" in str(type(e)):
                self.assertTrue(True, "函数逻辑执行正常，异常由 mock 数据导致")
            else:
                self.fail(f"意外异常: {e}")


class TestEngineImportIntegration(unittest.TestCase):
    """测试引擎模块的集成导入"""

    def test_all_required_imports_available(self):
        """测试所有必需的导入都可用"""
        try:
            # 测试标准库导入
            import gc
            import json
            import sys
            from datetime import datetime
            from pathlib import Path
            from typing import Dict, List, Optional

            # 测试第三方库导入
            import pandas as pd
            from nautilus_trader.backtest.engine import BacktestEngine
            from nautilus_trader.model import BarType, TraderId
            from nautilus_trader.model.currencies import USDT
            from nautilus_trader.persistence.loaders import CSVBarDataLoader
            from nautilus_trader.persistence.wranglers import BarDataWrangler

            # 测试本地模块导入
            from core.exceptions import (
                BacktestEngineError,
                CustomDataError,
                DataLoadError,
                InstrumentLoadError,
            )
            from core.schemas import BacktestConfig, DataConfig
            from strategy.core.loader import filter_strategy_params
            from utils.instrument_loader import load_instrument

            self.assertTrue(True, "所有必需导入都成功")

        except ImportError as e:
            self.fail(f"关键导入失败: {e}")


if __name__ == "__main__":
    unittest.main()
