#!/usr/bin/env python3
"""分析回测结果，找出 PNL 最高的结果"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

def parse_backtest_result(file_path: Path) -> Dict[str, Any]:
    """解析单个回测结果文件"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        # 提取关键信息
        result = {
            'file': file_path.name,
            'file_path': str(file_path),
            'file_mtime': datetime.fromtimestamp(file_path.stat().st_mtime),
            'pnl': None,
            'total_pnl': None,
            'return_pct': None,
            'sharpe_ratio': None,
            'max_drawdown': None,
            'win_rate': None,
            'total_trades': None,
        }

        # 从 pnl.USDT 字段提取 PNL
        if 'pnl' in data and 'USDT' in data['pnl']:
            pnl_data = data['pnl']['USDT']
            result['pnl'] = pnl_data.get('PnL (total)')
            result['total_pnl'] = pnl_data.get('PnL (total)')
            result['return_pct'] = pnl_data.get('PnL% (total)')
            result['win_rate'] = pnl_data.get('Win Rate')

        # 从 returns 字段提取其他指标
        if 'returns' in data:
            returns_data = data['returns']
            result['sharpe_ratio'] = returns_data.get('Sharpe Ratio (252 days)')
            result['max_drawdown'] = returns_data.get('Max Drawdown')

        # 从 performance 字段提取交易数量
        if 'performance' in data:
            perf_data = data['performance']
            result['total_trades'] = perf_data.get('total_trades')
            if result['sharpe_ratio'] is None:
                result['sharpe_ratio'] = perf_data.get('sharpe_ratio')

        return result
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None

def main():
    results_dir = Path('./output/backtest/result')

    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}")
        return

    # 解析所有结果文件
    all_results = []
    for json_file in results_dir.glob('*.json'):
        result = parse_backtest_result(json_file)
        if result and result['pnl'] is not None:
            all_results.append(result)

    if not all_results:
        print("No valid results found")
        return

    # 按 PNL 排序
    all_results.sort(key=lambda x: float(x['pnl']) if x['pnl'] else 0, reverse=True)

    # 显示前 10 个最佳结果
    print("=" * 120)
    print("Top 10 Backtest Results by PNL")
    print("=" * 120)
    print(f"{'Rank':<5} {'File':<50} {'PNL':<15} {'Return %':<12} {'Sharpe':<10} {'Trades':<8} {'File Time':<20}")
    print("-" * 120)

    for i, result in enumerate(all_results[:10], 1):
        pnl_str = f"{result['pnl']:.2f}" if result['pnl'] else "N/A"
        return_str = f"{result['return_pct']:.2f}%" if result['return_pct'] else "N/A"
        sharpe_str = f"{result['sharpe_ratio']:.2f}" if result['sharpe_ratio'] else "N/A"
        trades_str = str(result['total_trades']) if result['total_trades'] else "N/A"
        time_str = result['file_mtime'].strftime('%Y-%m-%d %H:%M:%S')

        print(f"{i:<5} {result['file']:<50} {pnl_str:<15} {return_str:<12} {sharpe_str:<10} {trades_str:<8} {time_str:<20}")

    print("\n" + "=" * 120)
    print("Detailed Information for Top 3 Results")
    print("=" * 120)

    for i, result in enumerate(all_results[:3], 1):
        print(f"\n--- Rank {i} ---")
        print(f"File: {result['file']}")
        print(f"File Path: {result['file_path']}")
        print(f"File Modified Time: {result['file_mtime']}")
        print(f"PNL: {result['pnl']}")
        print(f"Return %: {result['return_pct']}")
        print(f"Sharpe Ratio: {result['sharpe_ratio']}")
        print(f"Max Drawdown: {result['max_drawdown']}")
        print(f"Win Rate: {result['win_rate']}")
        print(f"Total Trades: {result['total_trades']}")

if __name__ == '__main__':
    main()
