"""
符号解析工具模块单元测试

测试内容：
1. resolve_symbol_and_type() - 符号解析和市场类型识别
2. parse_timeframe() - 时间周期解析
3. 边界情况和错误处理
4. 不同交易所格式支持

Usage:
    uv run python -m unittest tests.test_symbol_parser -v
"""

import unittest

from nautilus_trader.model.enums import BarAggregation

from utils.symbol_parser import parse_timeframe, resolve_symbol_and_type


class TestSymbolParser(unittest.TestCase):
    """符号解析工具测试类"""

    def test_resolve_symbol_and_type_spot(self):
        """测试现货交易对解析"""
        # 标准现货格式
        symbol, market_type = resolve_symbol_and_type("BTC/USDT")
        self.assertEqual(symbol, "BTC/USDT")
        self.assertEqual(market_type, "spot")

        symbol, market_type = resolve_symbol_and_type("ETH/BTC")
        self.assertEqual(symbol, "ETH/BTC")
        self.assertEqual(market_type, "spot")

    def test_resolve_symbol_and_type_usdt_perpetual(self):
        """测试USDT永续合约解析"""
        # USDT永续合约
        symbol, market_type = resolve_symbol_and_type("BTCUSDT")
        self.assertEqual(symbol, "BTC/USDT:USDT")
        self.assertEqual(market_type, "swap")

        symbol, market_type = resolve_symbol_and_type("ETHUSDT")
        self.assertEqual(symbol, "ETH/USDT:USDT")
        self.assertEqual(market_type, "swap")

        symbol, market_type = resolve_symbol_and_type("SOLUSDT")
        self.assertEqual(symbol, "SOL/USDT:USDT")
        self.assertEqual(market_type, "swap")

    def test_resolve_symbol_and_type_usd_perpetual(self):
        """测试USD永续合约解析"""
        # USD永续合约
        symbol, market_type = resolve_symbol_and_type("BTCUSD")
        self.assertEqual(symbol, "BTC/USD:BTC")
        self.assertEqual(market_type, "swap")

        symbol, market_type = resolve_symbol_and_type("ETHUSD")
        self.assertEqual(symbol, "ETH/USD:ETH")
        self.assertEqual(market_type, "swap")

    def test_resolve_symbol_and_type_case_insensitive(self):
        """测试大小写不敏感处理"""
        # 小写输入
        symbol, market_type = resolve_symbol_and_type("btcusdt")
        self.assertEqual(symbol, "BTC/USDT:USDT")
        self.assertEqual(market_type, "swap")

        # 混合大小写
        symbol, market_type = resolve_symbol_and_type("EthUsdt")
        self.assertEqual(symbol, "ETH/USDT:USDT")
        self.assertEqual(market_type, "swap")

    def test_resolve_symbol_and_type_other_formats(self):
        """测试其他格式的符号"""
        # 不以USDT或USD结尾的符号，按swap处理
        symbol, market_type = resolve_symbol_and_type("BTCETH")
        self.assertEqual(symbol, "BTCETH")
        self.assertEqual(market_type, "swap")

        symbol, market_type = resolve_symbol_and_type("CUSTOM")
        self.assertEqual(symbol, "CUSTOM")
        self.assertEqual(market_type, "swap")

    def test_parse_timeframe_minutes(self):
        """测试分钟级时间周期解析"""
        agg, period = parse_timeframe("1m")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("5m")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 5)

        agg, period = parse_timeframe("15m")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 15)

        agg, period = parse_timeframe("30m")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 30)

    def test_parse_timeframe_hours(self):
        """测试小时级时间周期解析"""
        agg, period = parse_timeframe("1h")
        self.assertEqual(agg, BarAggregation.HOUR)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("4h")
        self.assertEqual(agg, BarAggregation.HOUR)
        self.assertEqual(period, 4)

        agg, period = parse_timeframe("12h")
        self.assertEqual(agg, BarAggregation.HOUR)
        self.assertEqual(period, 12)

    def test_parse_timeframe_days(self):
        """测试日级时间周期解析"""
        agg, period = parse_timeframe("1d")
        self.assertEqual(agg, BarAggregation.DAY)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("7d")
        self.assertEqual(agg, BarAggregation.DAY)
        self.assertEqual(period, 7)

    def test_parse_timeframe_weeks(self):
        """测试周级时间周期解析"""
        agg, period = parse_timeframe("1w")
        self.assertEqual(agg, BarAggregation.WEEK)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("2w")
        self.assertEqual(agg, BarAggregation.WEEK)
        self.assertEqual(period, 2)

    def test_parse_timeframe_single_char(self):
        """测试单字符时间周期解析"""
        # 只有单位字符，默认period=1
        agg, period = parse_timeframe("m")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("h")
        self.assertEqual(agg, BarAggregation.HOUR)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("d")
        self.assertEqual(agg, BarAggregation.DAY)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("w")
        self.assertEqual(agg, BarAggregation.WEEK)
        self.assertEqual(period, 1)

    def test_parse_timeframe_invalid_unit(self):
        """测试无效时间单位的默认处理"""
        # 无效单位应该返回默认的MINUTE/1
        agg, period = parse_timeframe("5x")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("invalid")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 1)

    def test_parse_timeframe_edge_cases(self):
        """测试边界情况"""
        # 空字符串
        agg, period = parse_timeframe("")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 1)

        # 只有数字没有单位
        agg, period = parse_timeframe("60")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 1)

        # 大写字母
        agg, period = parse_timeframe("1H")
        self.assertEqual(agg, BarAggregation.HOUR)
        self.assertEqual(period, 1)

        agg, period = parse_timeframe("1D")
        self.assertEqual(agg, BarAggregation.DAY)
        self.assertEqual(period, 1)

    def test_parse_timeframe_large_periods(self):
        """测试大数值周期"""
        agg, period = parse_timeframe("60m")
        self.assertEqual(agg, BarAggregation.MINUTE)
        self.assertEqual(period, 60)

        agg, period = parse_timeframe("24h")
        self.assertEqual(agg, BarAggregation.HOUR)
        self.assertEqual(period, 24)

    def test_resolve_symbol_comprehensive(self):
        """测试符号解析的综合情况"""
        test_cases = [
            # (输入, 期望输出符号, 期望市场类型)
            ("BTC/USDT", "BTC/USDT", "spot"),
            ("ETH/BTC", "ETH/BTC", "spot"),
            ("BTCUSDT", "BTC/USDT:USDT", "swap"),
            ("ETHUSDT", "ETH/USDT:USDT", "swap"),
            ("BTCUSD", "BTC/USD:BTC", "swap"),
            ("ETHUSD", "ETH/USD:ETH", "swap"),
            ("btcusdt", "BTC/USDT:USDT", "swap"),
            ("CUSTOM", "CUSTOM", "swap"),
        ]

        for input_symbol, expected_symbol, expected_type in test_cases:
            with self.subTest(input_symbol=input_symbol):
                symbol, market_type = resolve_symbol_and_type(input_symbol)
                self.assertEqual(symbol, expected_symbol)
                self.assertEqual(market_type, expected_type)

    def test_parse_timeframe_comprehensive(self):
        """测试时间周期解析的综合情况"""
        test_cases = [
            # (输入, 期望聚合类型, 期望周期)
            ("1m", BarAggregation.MINUTE, 1),
            ("5m", BarAggregation.MINUTE, 5),
            ("15m", BarAggregation.MINUTE, 15),
            ("30m", BarAggregation.MINUTE, 30),
            ("1h", BarAggregation.HOUR, 1),
            ("4h", BarAggregation.HOUR, 4),
            ("1d", BarAggregation.DAY, 1),
            ("1w", BarAggregation.WEEK, 1),
            ("m", BarAggregation.MINUTE, 1),
            ("h", BarAggregation.HOUR, 1),
            ("invalid", BarAggregation.MINUTE, 1),
        ]

        for timeframe, expected_agg, expected_period in test_cases:
            with self.subTest(timeframe=timeframe):
                agg, period = parse_timeframe(timeframe)
                self.assertEqual(agg, expected_agg)
                self.assertEqual(period, expected_period)


if __name__ == "__main__":
    unittest.main()
