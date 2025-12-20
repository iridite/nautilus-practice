import ccxt
import pandas as pd
import argparse
import time
import sys
from pathlib import Path
from datetime import datetime, timezone

def parse_arguments():
    parser = argparse.ArgumentParser(description='Fetch OHLCV and Funding Rate data from Crypto Exchanges via CCXT.')
    
    # 1. 交易标的
    parser.add_argument('--symbol', '-s', type=str, required=True, help='Trading symbol, e.g., ETH/USDT (Spot) or ETHUSDT (Perp)')
    
    # 2. 起始时间
    parser.add_argument('--start', type=str, required=True, help='Start date (YYYY-MM-DD)')
    
    # 结束时间 (默认为今天零点)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d')
    parser.add_argument('--end', type=str, default=today, help='End date (YYYY-MM-DD), defaults to today 00:00')
    
    # 3. 时间粒度
    parser.add_argument('--timeframe', type=str, default='1h', help='Timeframe interval, e.g., 5m, 1h, 1d')

    # 4. 指定交易所 (新增)
    parser.add_argument('--exchange', type=str, default='binance', choices=['binance', 'okx'], 
                        help='Exchange ID (binance or okx). Default is binance.')
    
    return parser.parse_args()

def get_ms_timestamp(date_str):
    """将 YYYY-MM-DD 字符串转换为毫秒级时间戳 (UTC)"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

def resolve_symbol_and_type(input_symbol):
    """
    解析输入标的，返回 (ccxt_unified_symbol, market_type)
    
    策略：
    1. 输入含 '/': 认为是现货。
    2. 输入不含 '/': 认为是永续合约，尝试转换为 CCXT 的统一格式 Base/Quote:Settle。
       这对于 Binance 和 OKX 都是通用的。
    """
    if '/' in input_symbol:
        # 现货: ETH/USDT
        return input_symbol, 'spot'
    else:
        # 永续合约: ETHUSDT -> 转换为 ccxt 统一格式
        # 逻辑：假设是以 USDT 结尾的 U本位合约
        if input_symbol.upper().endswith('USDT'):
            base = input_symbol.upper().replace('USDT', '')
            # CCXT 统一格式: BASE/QUOTE:SETTLE
            # 例如: ETH/USDT:USDT
            ccxt_symbol = f"{base}/USDT:USDT"
            return ccxt_symbol, 'swap'
        
        # 逻辑：假设是以 USD 结尾的 币本位合约
        elif input_symbol.upper().endswith('USD'):
            base = input_symbol.upper().replace('USD', '')
            # 例如: ETH/USD:ETH
            ccxt_symbol = f"{base}/USD:{base}"
            return ccxt_symbol, 'swap'
        
        else:
            # 无法自动解析，直接尝试原样请求
            return input_symbol, 'swap'

def fetch_ohlcv_data(exchange, symbol, timeframe, since, limit_ms):
    """循环抓取 OHLCV 数据"""
    all_ohlcv = []
    current_since = since
    
    print(f"[*] [{exchange.id}] Fetching OHLCV for {symbol} from {datetime.fromtimestamp(since/1000, timezone.utc)}...")

    while current_since < limit_ms:
        try:
            # OKX 和 Binance 都支持 limit 参数，但最大值不同，100 是安全值，但为了速度设为 100 (OKX max 100 for candles usually, Binance 1000)
            # 为了兼容性，我们可以让 ccxt 自动处理，或者手动设一个小一点的值
            # OKX 的 fetch_ohlcv limit 默认通常是 100 (历史数据)
            limit_param = 100 if exchange.id == 'okx' else 1000
            
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=current_since, limit=limit_param)
            
            if not ohlcv:
                print(f"    No more data found at {current_since}.")
                break
            
            last_timestamp = ohlcv[-1][0]
            
            # 防止死循环：如果获取到的数据都是旧的
            if last_timestamp < current_since:
                break
                
            # 去重：有时交易所会返回包含 current_since 的数据
            new_data = [x for x in ohlcv if x[0] >= current_since]
            if not new_data:
                break

            all_ohlcv.extend(new_data)
            
            # 更新下一次抓取的起点：最后一条数据时间 + 1ms
            current_since = all_ohlcv[-1][0] + 1
            
            # 进度显示
            last_date = datetime.fromtimestamp(current_since/1000, timezone.utc)
            print(f"    Fetched up to {last_date} ({len(all_ohlcv)} candles)", end='\r')
            
            if current_since >= limit_ms:
                break
                
            time.sleep(exchange.rateLimit / 1000) 
            
        except Exception as e:
            print(f"\n[!] Error fetching OHLCV: {e}")
            # 对于某些错误（如网络中断），可以考虑重试，这里简单处理为退出循环
            break
            
    print(f"\n[*] OHLCV fetch complete. Total candles: {len(all_ohlcv)}")
    
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df = df[df['timestamp'] < limit_ms]
    return df

def fetch_funding_data(exchange, symbol, since, limit_ms):
    """循环抓取资金费率历史数据"""
    all_funding = []
    current_since = since
    
    print(f"[*] [{exchange.id}] Fetching Funding Rates for {symbol}...")
    
    # 检查交易所是否支持
    if not exchange.has['fetchFundingRateHistory']:
        print(f"[!] Exchange {exchange.id} does not support fetchFundingRateHistory via CCXT standard API.")
        return pd.DataFrame()

    while current_since < limit_ms:
        try:
            limit_param = 100 if exchange.id == 'okx' else 1000
            
            funding = exchange.fetch_funding_rate_history(symbol, since=current_since, limit=limit_param)
            
            if not funding:
                break
            
            # 过滤掉早于 current_since 的数据（防止死循环）
            new_funding = [f for f in funding if f['timestamp'] >= current_since]
            if not new_funding:
                break
                
            all_funding.extend(new_funding)
            
            last_timestamp = new_funding[-1]['timestamp']
            current_since = last_timestamp + 1
            
            last_date = datetime.fromtimestamp(last_timestamp/1000, timezone.utc)
            print(f"    Fetched funding up to {last_date}", end='\r')
            
            if last_timestamp >= limit_ms:
                break
                
            time.sleep(exchange.rateLimit / 1000)
            
        except Exception as e:
            print(f"\n[!] Error fetching Funding Rate: {e}")
            break

    print(f"\n[*] Funding rate fetch complete. Total records: {len(all_funding)}")
    
    if not all_funding:
        return pd.DataFrame()

    funding_data = []
    for f in all_funding:
        funding_data.append({
            'timestamp': f['timestamp'],
            'fundingRate': f['fundingRate']
        })
    
    df = pd.DataFrame(funding_data)
    df = df.drop_duplicates(subset=['timestamp']) # 去重
    df = df[df['timestamp'] < limit_ms]
    return df

def main():
    args = parse_arguments()
    
    # 1. 动态初始化交易所
    exchange_class = getattr(ccxt, args.exchange)
    exchange = exchange_class({
        'enableRateLimit': True,
        # 这里的 options 主要是为了 Binance 的默认行为，OKX 对此不敏感但也不会报错
        'options': {'defaultType': 'future'} 
    })
    
    # 2. 解析参数与符号
    raw_symbol = args.symbol
    ccxt_symbol, market_type = resolve_symbol_and_type(raw_symbol)
    
    # 3. 设置时间
    start_ms = get_ms_timestamp(args.start)
    end_ms = get_ms_timestamp(args.end)
    
    print(f"--- Configuration ---")
    print(f"Exchange: {args.exchange.upper()}")
    print(f"Raw Input: {raw_symbol}")
    print(f"Target Symbol: {ccxt_symbol}")
    print(f"Type: {market_type.upper()}")
    print(f"Range: {args.start} to {args.end}")
    print(f"---------------------")

    # 4. 加载市场
    try:
        exchange.load_markets()
    except Exception as e:
        print(f"[!] Failed to load markets: {e}")
        # 如果是因为网络问题，脚本会在这里终止
        return

    # 验证符号是否存在于该交易所
    if ccxt_symbol not in exchange.markets:
        print(f"[!] Error: Symbol '{ccxt_symbol}' not found in {args.exchange}.")
        print(f"    Possible reasons: Invalid symbol, or conversion from '{raw_symbol}' failed.")
        print(f"    Available symbols example: {list(exchange.markets.keys())[:5]}...")
        return

    # 5. 获取 OHLCV
    ohlcv_df = fetch_ohlcv_data(exchange, ccxt_symbol, args.timeframe, start_ms, end_ms)
    
    if ohlcv_df.empty:
        print("[!] No OHLCV data fetched. Exiting.")
        return

    # 6. 如果是永续合约，获取资金费率并合并
    if market_type == 'swap':
        funding_df = fetch_funding_data(exchange, ccxt_symbol, start_ms, end_ms)
        
        if not funding_df.empty:
            # 合并：以 OHLCV 为主，左连接资金费率
            # 资金费率在非结算时间点将为 NaN
            ohlcv_df = pd.merge(ohlcv_df, funding_df, on='timestamp', how='left')
        else:
            ohlcv_df['fundingRate'] = None
            
    # 7. 数据格式化
    ohlcv_df['datetime'] = pd.to_datetime(ohlcv_df['timestamp'], unit='ms')
    
    cols = ['datetime', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
    if 'fundingRate' in ohlcv_df.columns:
        cols.append('fundingRate')
    ohlcv_df = ohlcv_df[cols]

    # 8. 保存文件
    current_dir = Path(__file__).parent
    output_dir = current_dir.parent / 'data'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    safe_symbol = raw_symbol.replace('/', '') 
    # 文件名增加 exchange 标识，防止同名币种覆盖
    filename = f"{args.exchange}-{safe_symbol}-{args.timeframe}-{args.start}_{args.end}.csv"
    output_path = output_dir / filename
    
    ohlcv_df.to_csv(output_path, index=False)
    print(f"\n[√] Data saved to: {output_path}")

if __name__ == "__main__":
    main()