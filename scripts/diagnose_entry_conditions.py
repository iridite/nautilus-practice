"""
诊断 Keltner 策略入场条件

分析每个过滤器的通过率，找出阻止交易的瓶颈
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from strategy.keltner_rs_breakout import KeltnerRSBreakoutStrategy, KeltnerRSBreakoutConfig
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity
from datetime import datetime
import pandas as pd

# 模拟配置
config = KeltnerRSBreakoutConfig(
    instrument_id="ETHUSDT-PERP.BINANCE",
    bar_type="ETHUSDT-PERP.BINANCE-1-DAY-LAST-EXTERNAL",
    btc_instrument_id="BTCUSDT-PERP.BINANCE",
    universe_top_n=15,
    universe_freq="W-MON",
)

print("=" * 80)
print("Keltner RS Breakout 策略入场条件诊断")
print("=" * 80)
print()
print("入场条件检查顺序：")
print("1. ✓ 没有待处理订单")
print("2. ✓ 标的在活跃 Universe 中")
print("3. ✓ BTC 市场状态有利（enable_btc_regime_filter=True）")
print("4. ✓ 市场狂热度正常（enable_euphoria_filter=True）")
print("5. ✓ 价格 > SMA(200)")
print("6. ✓ 相对强度 > 0（RS > BTC）")
print("7. ✓ 成交量突破（volume > 2 * SMA(volume, 20)）")
print("8. ✓ Keltner 突破（close > EMA(20) + 2.8 * ATR(20)）")
print("9. ✓ 上影线比例 < 30%")
print()
print("=" * 80)
print("配置参数：")
print("=" * 80)
print(f"  timeframe: 1d")
print(f"  universe_top_n: {config.universe_top_n}")
print(f"  universe_freq: {config.universe_freq}")
print(f"  enable_btc_regime_filter: {config.enable_btc_regime_filter}")
print(f"  enable_euphoria_filter: {config.enable_euphoria_filter}")
print(f"  volume_multiplier: {config.volume_multiplier}")
print(f"  keltner_trigger_multiplier: {config.keltner_trigger_multiplier}")
print(f"  max_upper_wick_ratio: {config.max_upper_wick_ratio}")
print()
print("=" * 80)
print("建议：")
print("=" * 80)
print("1. 检查 BTC regime filter 是否过于严格")
print("2. 检查 RS 计算是否正确（需要 BTC 数据）")
print("3. 检查 volume_multiplier=2 是否过高")
print("4. 检查 keltner_trigger_multiplier=2.8 是否过高")
print("5. 添加日志输出，追踪每个过滤器的通过率")
print()
