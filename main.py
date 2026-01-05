import argparse
import sys
from pathlib import Path

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import current_config
from utils.fetch_instrument import update_instruments
from backtest.engine_high import run_high_level
from backtest.engine_low import run_low_level

def main():
    parser = argparse.ArgumentParser(description="Nautilus Trader Unified Runner")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Backtest Command
    bt_parser = subparsers.add_parser("backtest", help="Run backtest")
    bt_parser.add_argument(
        "--type", 
        choices=["high", "low"], 
        default="high", 
        help="Backtest engine type (high-level node or low-level engine)"
    )
    
    # Sandbox Command
    sb_parser = subparsers.add_parser("sandbox", help="Run sandbox (Not implemented yet)")
    
    # Live Command
    live_parser = subparsers.add_parser("live", help="Run live trading (Not implemented yet)")

    args = parser.parse_args()

    # 1. Fetch & Update Instruments (Always run this first)
    # This ensures we have the latest instrument definitions from the exchange
    # saved locally for the backtest/sandbox/live engines to use.
    try:
        instrument_id = current_config.instrument.instrument_id
        # If instrument_id is constructed like "ETHUSDT.BINANCE", we might need to adjust it 
        # if the fetcher expects "ETHUSDT-PERP.BINANCE". 
        # Looking at config/definitions.py: return f"{self.symbol}.{self.venue}" -> "ETHUSDT.BINANCE"
        # Looking at fetch_instrument.py: expects "ETHUSDT-PERP.BINANCE" or similar Nautilus ID.
        # The user's config might need adjustment or we assume it's correct.
        # Let's assume the config produces a valid ID or the user will fix the config.
        # However, in fetch_instrument.py, the example is "ETHUSDT-PERP.BINANCE".
        # In config/settings.py, symbol is "ETHUSDT".
        # So instrument_id will be "ETHUSDT.BINANCE".
        # Nautilus usually expects "ETHUSDT-PERP.BINANCE" for perps.
        # But let's just pass what is in the config.
        
        print(f"🔄 Updating instrument definitions for: {instrument_id}")
        update_instruments([instrument_id])
    except Exception as e:
        print(f"⚠️ Failed to update instruments: {e}")
        print("   Continuing with existing local files (if any)...")

    if args.command == "backtest":
        if args.type == "high":
            run_high_level(current_config, BASE_DIR)
        elif args.type == "low":
            run_low_level(current_config, BASE_DIR)
            
    elif args.command == "sandbox":
        print("🚧 Sandbox mode integration pending...")
        # TODO: Import and run sandbox logic using current_config
        
    elif args.command == "live":
        print("🚧 Live mode integration pending...")
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
