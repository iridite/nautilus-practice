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

from core.exceptions import SymbolParsingError, TimeframeParsingError
from utils.symbol_parser import (
    parse_timeframe,
    resolve_symbol_and_type,
    normalize_symbol,
    extract_base_quote,
    is_perpetual_contract,
    convert_timeframe_to_seconds,
    convert_nautilus_to_ccxt_timeframe,
)


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

    def test_normalize_symbol_binance(self):
        """测试 Binance 格式标准化"""
        # 现货
        result = normalize_symbol("BTC/USDT", "binance")
        self.assertEqual(result, "BTCUSDT")

        # 永续合约
        result = normalize_symbol("BTC/USDT:USDT", "binance")
        self.assertEqual(result, "BTCUSDT")

        result = normalize_symbol("ETHUSDT", "binance")
        self.assertEqual(result, "ETHUSDT")

    def test_normalize_symbol_okx(self):
        """测试 OKX 格式标准化"""
        # 现货
        result = normalize_symbol("BTC/USDT", "okx")
        self.assertEqual(result, "BTC-USDT")

        # 永续合约
        result = normalize_symbol("BTC/USDT:USDT", "okx")
        self.assertEqual(result, "BTC-USDT-SWAP")

        result = normalize_symbol("ETHUSDT", "okx")
        self.assertEqual(result, "ETH-USDT-SWAP")

    def test_normalize_symbol_default(self):
        """测试默认交易所格式"""
        result = normalize_symbol("BTCUSDT", "unknown_exchange")
        self.assertEqual(result, "BTC/USDT:USDT")

    def test_extract_base_quote(self):
        """测试提取基础货币和计价货币"""
        # 标准格式
        base, quote = extract_base_quote("BTC/USDT")
        self.assertEqual(base, "BTC")
        self.assertEqual(quote, "USDT")

        # 永续合约格式
        base, quote = extract_base_quote("BTC/USDT:USDT")
        self.assertEqual(base, "BTC")
        self.assertEqual(quote, "USDT")

        # 简化格式
        base, quote = extract_base_quote("ETHUSDT")
        self.assertEqual(base, "ETH")
        self.assertEqual(quote, "USDT")

    def test_is_perpetual_contract(self):
        """测试判断是否为永续合约"""
        # 永续合约
        self.assertTrue(is_perpetual_contract("BTCUSDT"))
        self.assertTrue(is_perpetual_contract("BTC/USDT:USDT"))
        self.assertTrue(is_perpetual_contract("ETHUSD"))

        # 现货
        self.assertFalse(is_perpetual_contract("BTC/USDT"))
        self.assertFalse(is_perpetual_contract("ETH/BTC"))

    def test_convert_timeframe_to_seconds(self):
        """测试时间周期转换为秒数"""
        self.assertEqual(convert_timeframe_to_seconds("1m"), 60)
        self.assertEqual(convert_timeframe_to_seconds("5m"), 300)
        self.assertEqual(convert_timeframe_to_seconds("1h"), 3600)
        self.assertEqual(convert_timeframe_to_seconds("4h"), 14400)
        self.assertEqual(convert_timeframe_to_seconds("1d"), 86400)
        self.assertEqual(convert_timeframe_to_seconds("1w"), 604800)

    def test_convert_nautilus_to_ccxt_timeframe(self):
        """测试 Nautilus 格式转换为 CCXT 格式"""
        result = convert_nautilus_to_ccxt_timeframe(BarAggregation.MINUTE, 1)
        self.assertEqual(result, "1m")

        result = convert_nautilus_to_ccxt_timeframe(BarAggregation.MINUTE, 5)
        self.assertEqual(result, "5m")

        result = convert_nautilus_to_ccxt_timeframe(BarAggregation.HOUR, 1)
        self.assertEqual(result, "1h")

        result = convert_nautilus_to_ccxt_timeframe(BarAggregation.DAY, 1)
        self.assertEqual(result, "1d")

        result = convert_nautilus_to_ccxt_timeframe(BarAggregation.WEEK, 1)
        self.assertEqual(result, "1w")

    def test_error_handling(self):
        """测试错误处理"""
        # 测试无效符号
        with self.assertRaises(SymbolParsingError):
            resolve_symbol_and_type("")

    def test_edge_cases_btc_eth_suffix(self):
        """测试 BTC/ETH 后缀的边界情况"""
        # LINKBTC (7个字符) 应该被解析为 LINK/BTC 现货
        symbol, market_type = resolve_symbol_and_type("LINKBTC")
        self.assertEqual(symbol, "LINK/BTC")
        self.assertEqual(market_type, "spot")

        # LINKETH (7个字符) 应该被解析为 LINK/ETH 现货
        symbol, market_type = resolve_symbol_and_type("LINKETH")
        self.assertEqual(symbol, "LINK/ETH")
        self.assertEqual(market_type, "spot")

        # ETHBTC (6个字符，不满足 > 6) 应该被当作 swap
        symbol, market_type = resolve_symbol_and_type("ETHBTC")
        self.assertEqual(symbol, "ETHBTC")
        self.assertEqual(market_type, "swap")

        # BTCETH (6个字符，不满足 > 6) 应该被当作 swap
        symbol, market_type = resolve_symbol_and_type("BTCETH")
        self.assertEqual(symbol, "BTCETH")
        self.assertEqual(market_type, "swap")

    def test_short_symbols(self):
        """测试短符号"""
        # 太短的 USDT 后缀符号
        with self.assertRaises(SymbolParsingError):
            resolve_symbol_and_type("USDT")

        # 太短的 USD 后缀符号
        with self.assertRaises(SymbolParsingError):
            resolve_symbol_and_type("USD")


if __name__ == "__main__":
    unittest.main()
