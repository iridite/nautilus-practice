"""
测试 core/schemas.py 配置数据模型
"""

import pytest
from decimal import Decimal
from pathlib import Path
from pydantic import ValidationError

from core.schemas import (
    InstrumentType,
    InstrumentConfig,
    DataConfig,
    TradingConfig,
    BacktestPeriodConfig,
    LoggingConfig,
    FileCleanupConfig,
    StrategyConfig,
    SandboxConfig,
    LiveConfig,
    ActiveConfig,
)
from nautilus_trader.model.enums import BarAggregation, PriceType


class TestInstrumentType:
    """测试 InstrumentType 枚举"""

    def test_instrument_types(self):
        """测试所有合约类型"""
        assert InstrumentType.SPOT.value == "SPOT"
        assert InstrumentType.FUTURES.value == "FUTURES"
        assert InstrumentType.SWAP.value == "SWAP"
        assert InstrumentType.OPTION.value == "OPTION"


class TestInstrumentConfig:
    """测试 InstrumentConfig 配置"""

    def test_default_values(self):
        """测试默认值"""
        config = InstrumentConfig()
        assert config.type == InstrumentType.SWAP
        assert config.venue_name == "OKX"
        assert config.base_currency == "USDT"
        assert config.quote_currency == "ETH"
        assert config.leverage == 1

    def test_get_id_for_okx(self):
        """测试 OKX 交易所的 instrument_id 生成"""
        inst_id = InstrumentConfig.get_id_for(
            venue_name="OKX",
            base_currency="USDT",
            quote_currency="BTC",
            inst_type=InstrumentType.SWAP
        )
        assert inst_id == "BTC-USDT-SWAP.OKX"

    def test_get_id_for_binance_spot(self):
        """测试 Binance 现货的 instrument_id 生成"""
        inst_id = InstrumentConfig.get_id_for(
            venue_name="BINANCE",
            base_currency="USDT",
            quote_currency="ETH",
            inst_type=InstrumentType.SPOT
        )
        assert inst_id == "ETHUSDT.BINANCE"

    def test_get_id_for_binance_swap(self):
        """测试 Binance 永续合约的 instrument_id 生成"""
        inst_id = InstrumentConfig.get_id_for(
            venue_name="BINANCE",
            base_currency="USDT",
            quote_currency="BTC",
            inst_type=InstrumentType.SWAP
        )
        assert inst_id == "BTCUSDT-PERP.BINANCE"

    def test_get_id_for_unsupported_venue(self):
        """测试不支持的交易所"""
        with pytest.raises(ValueError, match="Unsupported venue"):
            InstrumentConfig.get_id_for(
                venue_name="UNKNOWN",
                base_currency="USDT",
                quote_currency="BTC",
                inst_type=InstrumentType.SWAP
            )

    def test_get_symbol(self):
        """测试获取交易对符号"""
        config = InstrumentConfig(quote_currency="BTC", base_currency="USDT")
        assert config.get_symbol() == "BTCUSDT"

    def test_instrument_id_property(self):
        """测试 instrument_id 属性"""
        config = InstrumentConfig(
            venue_name="OKX",
            quote_currency="ETH",
            base_currency="USDT",
            type=InstrumentType.SWAP
        )
        assert config.instrument_id == "ETH-USDT-SWAP.OKX"


class TestDataConfig:
    """测试 DataConfig 配置"""

    def test_default_values(self):
        """测试默认值"""
        config = DataConfig(csv_file_name="test.csv")
        assert config.bar_aggregation == BarAggregation.HOUR
        assert config.bar_period == 1
        assert config.price_type == PriceType.LAST
        assert config.origination == "EXTERNAL"
        assert config.label == "main"

    def test_bar_type_str(self):
        """测试 bar_type 字符串生成"""
        config = DataConfig(
            csv_file_name="test.csv",
            bar_aggregation=BarAggregation.MINUTE,
            bar_period=5,
            price_type=PriceType.MID
        )
        assert config.bar_type_str == "5-MINUTE-MID-EXTERNAL"


class TestTradingConfig:
    """测试 TradingConfig 配置"""

    def test_default_values(self):
        """测试默认值"""
        config = TradingConfig()
        assert config.venue == "BINANCE"
        assert config.instrument_type == "SWAP"
        assert config.initial_balance == Decimal("100")
        assert config.currency == "USDT"
        assert config.main_timeframe == "1h"
        assert config.trend_timeframe == "4h"

    def test_validate_venue(self):
        """测试交易所验证"""
        config = TradingConfig(venue="okx")
        assert config.venue == "OKX"

        with pytest.raises(ValidationError):
            TradingConfig(venue="UNKNOWN")

    def test_validate_instrument_type(self):
        """测试合约类型验证"""
        config = TradingConfig(instrument_type="spot")
        assert config.instrument_type == "SPOT"

        with pytest.raises(ValidationError):
            TradingConfig(instrument_type="INVALID")

    def test_validate_initial_balance(self):
        """测试初始余额验证"""
        with pytest.raises(ValidationError, match="Initial balance must be positive"):
            TradingConfig(initial_balance=0)

        with pytest.raises(ValidationError):
            TradingConfig(initial_balance=-100)

    def test_validate_timeframe(self):
        """测试时间框架验证"""
        config = TradingConfig(main_timeframe="4h")
        assert config.main_timeframe == "4h"

        with pytest.raises(ValidationError):
            TradingConfig(main_timeframe="")

        with pytest.raises(ValidationError):
            TradingConfig(main_timeframe="4x")


class TestBacktestPeriodConfig:
    """测试 BacktestPeriodConfig 配置"""

    def test_valid_dates(self):
        """测试有效日期"""
        config = BacktestPeriodConfig(
            start_date="2024-01-01",
            end_date="2024-12-31"
        )
        assert config.start_date == "2024-01-01"
        assert config.end_date == "2024-12-31"

    def test_invalid_date_format(self):
        """测试无效日期格式"""
        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            BacktestPeriodConfig(
                start_date="01/01/2024",
                end_date="2024-12-31"
            )

    def test_start_after_end(self):
        """测试开始日期晚于结束日期"""
        with pytest.raises(ValidationError, match="start_date must be before end_date"):
            BacktestPeriodConfig(
                start_date="2024-12-31",
                end_date="2024-01-01"
            )


class TestLoggingConfig:
    """测试 LoggingConfig 配置"""

    def test_default_values(self):
        """测试默认值"""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.file_level == "DEBUG"
        assert config.components == {}
        assert config.components_only is True

    def test_validate_log_level(self):
        """测试日志级别验证"""
        config = LoggingConfig(level="warning")
        assert config.level == "WARNING"

        with pytest.raises(ValidationError):
            LoggingConfig(level="INVALID")


class TestFileCleanupConfig:
    """测试 FileCleanupConfig 配置"""

    def test_default_values(self):
        """测试默认值"""
        config = FileCleanupConfig()
        assert config.max_files_per_dir == 100
        assert config.enabled is True
        assert config.target_dirs == ["log", "output"]
        assert config.use_time_rotation is False
        assert config.keep_days == 7
        assert config.delete_days == 30

    def test_validate_max_files(self):
        """测试最大文件数验证"""
        with pytest.raises(ValidationError):
            FileCleanupConfig(max_files_per_dir=0)

    def test_validate_target_dirs(self):
        """测试目标目录验证"""
        with pytest.raises(ValidationError):
            FileCleanupConfig(target_dirs=[])

    def test_validate_keep_days(self):
        """测试保留天数验证"""
        with pytest.raises(ValidationError):
            FileCleanupConfig(keep_days=0)

    def test_validate_delete_days(self):
        """测试删除天数验证"""
        with pytest.raises(ValidationError):
            FileCleanupConfig(delete_days=0)

        # delete_days 必须大于等于 keep_days
        with pytest.raises(ValidationError):
            FileCleanupConfig(keep_days=10, delete_days=5)


class TestStrategyConfig:
    """测试 StrategyConfig 配置"""

    def test_valid_config(self):
        """测试有效配置"""
        config = StrategyConfig(
            name="TestStrategy",
            module_path="strategy.test",
            parameters={"param1": "value1"}
        )
        assert config.name == "TestStrategy"
        assert config.module_path == "strategy.test"
        assert config.parameters == {"param1": "value1"}

    def test_validate_name(self):
        """测试策略名称验证"""
        with pytest.raises(ValidationError, match="Strategy name cannot be empty"):
            StrategyConfig(name="", module_path="strategy.test")

        with pytest.raises(ValidationError):
            StrategyConfig(name="   ", module_path="strategy.test")

    def test_validate_module_path(self):
        """测试模块路径验证"""
        with pytest.raises(ValidationError, match="Module path cannot be empty"):
            StrategyConfig(name="Test", module_path="")


class TestSandboxConfig:
    """测试 SandboxConfig 配置"""

    def test_default_values(self):
        """测试默认值"""
        config = SandboxConfig()
        assert config.venue == "OKX"
        assert config.is_testnet is True
        assert config.instrument_ids == []

    def test_validate_venue(self):
        """测试交易所验证"""
        config = SandboxConfig(venue="binance")
        assert config.venue == "BINANCE"

        with pytest.raises(ValidationError):
            SandboxConfig(venue="UNKNOWN")

    def test_validate_instruments(self):
        """测试合约验证"""
        with pytest.raises(ValidationError, match="At least one instrument_id is required"):
            SandboxConfig(instrument_ids=[])


class TestLiveConfig:
    """测试 LiveConfig 配置"""

    def test_default_values(self):
        """测试默认值"""
        config = LiveConfig()
        assert config.venue == "BINANCE"
        assert config.instrument_ids == []
        assert config.reconciliation is True
        assert config.flush_cache_on_start is False

    def test_validate_venue(self):
        """测试交易所验证"""
        config = LiveConfig(venue="okx")
        assert config.venue == "OKX"

    def test_validate_instruments(self):
        """测试合约验证"""
        with pytest.raises(ValidationError):
            LiveConfig(instrument_ids=[])


class TestActiveConfig:
    """测试 ActiveConfig 配置"""

    def test_valid_config(self):
        """测试有效配置"""
        config = ActiveConfig(
            environment="dev",
            strategy="test_strategy",
            primary_symbol="BTCUSDT"
        )
        assert config.environment == "dev"
        assert config.strategy == "test_strategy"
        assert config.primary_symbol == "BTCUSDT"

    def test_validate_environment(self):
        """测试环境名称验证"""
        with pytest.raises(ValidationError, match="Environment cannot be empty"):
            ActiveConfig(environment="", strategy="test", primary_symbol="BTCUSDT")

    def test_validate_strategy(self):
        """测试策略名称验证"""
        with pytest.raises(ValidationError, match="Strategy cannot be empty"):
            ActiveConfig(environment="dev", strategy="", primary_symbol="BTCUSDT")

    def test_validate_primary_symbol(self):
        """测试主交易标的验证"""
        with pytest.raises(ValidationError, match="Primary symbol cannot be empty"):
            ActiveConfig(environment="dev", strategy="test", primary_symbol="")

        with pytest.raises(ValidationError, match="must end with 'USDT'"):
            ActiveConfig(environment="dev", strategy="test", primary_symbol="BTCUSD")

        # 应该自动转换为大写
        config = ActiveConfig(environment="dev", strategy="test", primary_symbol="btcusdt")
        assert config.primary_symbol == "BTCUSDT"

    def test_validate_timeframe(self):
        """测试时间框架验证（可选）"""
        config = ActiveConfig(
            environment="dev",
            strategy="test",
            primary_symbol="BTCUSDT",
            timeframe="4h"
        )
        assert config.timeframe == "4h"

        # None 应该被接受
        config = ActiveConfig(
            environment="dev",
            strategy="test",
            primary_symbol="BTCUSDT",
            timeframe=None
        )
        assert config.timeframe is None

    def test_validate_price_type(self):
        """测试价格类型验证（可选）"""
        config = ActiveConfig(
            environment="dev",
            strategy="test",
            primary_symbol="BTCUSDT",
            price_type="mid"
        )
        assert config.price_type == "MID"

        with pytest.raises(ValidationError):
            ActiveConfig(
                environment="dev",
                strategy="test",
                primary_symbol="BTCUSDT",
                price_type="INVALID"
            )

    def test_validate_origination(self):
        """测试数据来源验证（可选）"""
        config = ActiveConfig(
            environment="dev",
            strategy="test",
            primary_symbol="BTCUSDT",
            origination="internal"
        )
        assert config.origination == "INTERNAL"

        with pytest.raises(ValidationError):
            ActiveConfig(
                environment="dev",
                strategy="test",
                primary_symbol="BTCUSDT",
                origination="INVALID"
            )
