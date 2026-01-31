#!/usr/bin/env python3
"""测试多数据源获取器"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from utils.data_management.data_fetcher import DataFetcher

fetcher = DataFetcher()

# 测试Binance
print('Testing Binance API...')
df_binance = fetcher.fetch_ohlcv('BTCUSDT', '1h', source='binance')
print(f'✓ Binance: {len(df_binance)} rows')
print(df_binance.head(2))

# 测试CoinGecko
print('\nTesting CoinGecko API...')
df_cg = fetcher.fetch_ohlcv('BTC/USDT', '1d', source='coingecko')
print(f'✓ CoinGecko: {len(df_cg)} rows')
print(df_cg.head(2))

# 测试自动切换
print('\nTesting auto fallback...')
df_auto = fetcher.fetch_ohlcv('BTCUSDT', '1h', source='auto')
print(f'✓ Auto: {len(df_auto)} rows')

print('\n✅ All tests passed')
