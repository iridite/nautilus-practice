import argparse
import sys
from pathlib import Path

# Add workspace root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import current_config
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
