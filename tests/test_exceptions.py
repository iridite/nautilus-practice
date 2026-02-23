"""
测试 core/exceptions.py 统一异常体系
"""

import pytest
from core.exceptions import (
    NautilusPracticeError,
    ConfigError,
    ConfigValidationError,
    ConfigLoadError,
    UniverseParseError,
    InstrumentConfigError,
    DataError,
    DataValidationError,
    DataLoadError,
    DataFetchError,
    TimeColumnError,
    CatalogError,
    BacktestError,
    BacktestEngineError,
    InstrumentLoadError,
    StrategyConfigError,
    CustomDataError,
    ResultProcessingError,
    ValidationError,
    ParsingError,
    SymbolParsingError,
    TimeframeParsingError,
    PreflightError,
)


class TestBaseException:
    """测试基础异常类"""

    def test_base_exception(self):
        """测试基础异常"""
        exc = NautilusPracticeError("Test error")
        assert str(exc) == "Test error"
        assert isinstance(exc, Exception)

    def test_exception_with_cause(self):
        """测试异常链"""
        cause = ValueError("Original error")
        exc = NautilusPracticeError("Wrapped error", cause=cause)
        assert exc.cause == cause
        assert "caused by" in str(exc)


class TestConfigErrors:
    """测试配置相关异常"""

    def test_config_error(self):
        """测试配置错误基类"""
        exc = ConfigError("Config error")
        assert isinstance(exc, NautilusPracticeError)
        assert str(exc) == "Config error"

    def test_config_validation_error(self):
        """测试配置验证错误"""
        exc = ConfigValidationError("Invalid config", field="venue", value="INVALID")
        assert isinstance(exc, ConfigError)
        assert exc.field == "venue"
        assert exc.value == "INVALID"
        assert "venue" in str(exc)

    def test_config_validation_error_no_field(self):
        """测试无字段的配置验证错误"""
        exc = ConfigValidationError("Invalid config")
        assert exc.field is None
        assert exc.value is None

    def test_config_load_error(self):
        """测试配置加载错误"""
        exc = ConfigLoadError("Failed to load")
        assert isinstance(exc, ConfigError)

    def test_universe_parse_error(self):
        """测试 Universe 解析错误"""
        exc = UniverseParseError("Parse failed")
        assert isinstance(exc, ConfigError)

    def test_instrument_config_error(self):
        """测试合约配置错误"""
        exc = InstrumentConfigError("Invalid instrument")
        assert isinstance(exc, ConfigError)


class TestDataErrors:
    """测试数据相关异常"""

    def test_data_error(self):
        """测试数据错误基类"""
        exc = DataError("Data error")
        assert isinstance(exc, NautilusPracticeError)

    def test_data_validation_error(self):
        """测试数据验证错误"""
        exc = DataValidationError("Invalid data", field_name="price")
        assert isinstance(exc, DataError)
        assert exc.field_name == "price"
        assert "price" in str(exc)

    def test_data_validation_error_no_field(self):
        """测试无字段的数据验证错误"""
        exc = DataValidationError("Invalid data")
        assert exc.field_name is None

    def test_data_load_error(self):
        """测试数据加载错误"""
        exc = DataLoadError("Load failed", file_path="/data/btc.csv")
        assert isinstance(exc, DataError)
        assert exc.file_path == "/data/btc.csv"
        assert "btc.csv" in str(exc)

    def test_data_load_error_no_path(self):
        """测试无路径的数据加载错误"""
        exc = DataLoadError("Load failed")
        assert exc.file_path is None

    def test_data_fetch_error(self):
        """测试数据获取错误"""
        exc = DataFetchError("Fetch failed", source="OKX")
        assert isinstance(exc, DataError)
        assert exc.source == "OKX"
        assert "OKX" in str(exc)

    def test_data_fetch_error_no_source(self):
        """测试无来源的数据获取错误"""
        exc = DataFetchError("Fetch failed")
        assert exc.source is None

    def test_time_column_error(self):
        """测试时间列错误"""
        exc = TimeColumnError("Missing time column")
        assert isinstance(exc, DataError)
        assert isinstance(exc, DataLoadError)

    def test_catalog_error(self):
        """测试目录错误"""
        exc = CatalogError("Catalog error", catalog_path="/data/catalog")
        assert isinstance(exc, DataError)
        assert exc.catalog_path == "/data/catalog"
        assert "catalog" in str(exc)

    def test_catalog_error_no_path(self):
        """测试无路径的目录错误"""
        exc = CatalogError("Catalog error")
        assert exc.catalog_path is None


class TestBacktestErrors:
    """测试回测相关异常"""

    def test_backtest_error(self):
        """测试回测错误基类"""
        exc = BacktestError("Backtest error")
        assert isinstance(exc, NautilusPracticeError)

    def test_backtest_engine_error(self):
        """测试回测引擎错误"""
        exc = BacktestEngineError("Engine failed")
        assert isinstance(exc, BacktestError)

    def test_instrument_load_error(self):
        """测试合约加载错误"""
        exc = InstrumentLoadError("Load failed")
        assert isinstance(exc, BacktestError)

    def test_strategy_config_error(self):
        """测试策略配置错误"""
        exc = StrategyConfigError("Invalid strategy")
        assert isinstance(exc, BacktestError)

    def test_custom_data_error(self):
        """测试自定义数据错误"""
        exc = CustomDataError("Custom data error")
        assert isinstance(exc, BacktestError)

    def test_result_processing_error(self):
        """测试结果处理错误"""
        exc = ResultProcessingError("Processing failed")
        assert isinstance(exc, BacktestError)

    def test_validation_error(self):
        """测试验证错误"""
        exc = ValidationError("Validation failed")
        assert isinstance(exc, BacktestError)


class TestParsingErrors:
    """测试解析相关异常"""

    def test_parsing_error(self):
        """测试解析错误基类"""
        exc = ParsingError("Parse error")
        assert isinstance(exc, NautilusPracticeError)

    def test_symbol_parsing_error(self):
        """测试符号解析错误"""
        exc = SymbolParsingError("Invalid symbol")
        assert isinstance(exc, ParsingError)

    def test_timeframe_parsing_error(self):
        """测试时间框架解析错误"""
        exc = TimeframeParsingError("Invalid timeframe")
        assert isinstance(exc, ParsingError)


class TestPreflightError:
    """测试预检错误"""

    def test_preflight_error(self):
        """测试预检错误"""
        problems = ["API key missing", "Invalid venue"]
        exc = PreflightError(problems)
        assert isinstance(exc, NautilusPracticeError)
        assert exc.problems == problems
        assert "API key missing" in str(exc)
        assert "Invalid venue" in str(exc)

    def test_preflight_error_single_problem(self):
        """测试单个问题的预检错误"""
        exc = PreflightError(["Missing config"])
        assert len(exc.problems) == 1
        assert exc.problems[0] == "Missing config"


class TestExceptionChaining:
    """测试异常链功能"""

    def test_exception_with_cause(self):
        """测试带原因的异常"""
        original = ValueError("Original error")
        wrapped = DataLoadError("Failed to load data", cause=original)
        assert wrapped.cause == original
        assert "caused by" in str(wrapped)

    def test_nested_exception_chain(self):
        """测试嵌套异常链"""
        level1 = IOError("IO error")
        level2 = DataLoadError("Load error", cause=level1)
        level3 = BacktestEngineError("Engine error", cause=level2)

        assert level3.cause == level2
        assert level2.cause == level1


class TestExceptionAttributes:
    """测试异常属性"""

    def test_multiple_attributes(self):
        """测试多个属性"""
        exc = DataLoadError(
            "Load failed", file_path="/data/test.csv", cause=IOError("File not found")
        )
        assert exc.file_path == "/data/test.csv"
        assert isinstance(exc.cause, IOError)

    def test_optional_attributes(self):
        """测试可选属性"""
        exc = ConfigValidationError("Validation failed")
        assert exc.field is None

        exc_with_field = ConfigValidationError("Validation failed", field="venue")
        assert exc_with_field.field == "venue"

    def test_string_representation_with_attributes(self):
        """测试带属性的字符串表示"""
        exc = ConfigValidationError("Invalid value", field="venue", value="INVALID")
        str_repr = str(exc)
        assert "Invalid value" in str_repr
        assert "venue" in str_repr
        assert "INVALID" in str_repr
