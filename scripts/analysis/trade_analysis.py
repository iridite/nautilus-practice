#!/usr/bin/env python3
"""交易案例分析"""

import json
from pathlib import Path

def analyze_period(file_path, period_name):
    """分析单个时期的回测结果"""
    with open(file_path, 'r') as f:
        data = json.load(f)

    pnl_data = data.get('pnl', {}).get('USDT', {})
    returns_data = data.get('returns', {})
    performance = data.get('performance', {})

    result = {
        'period': period_name,
        'total_trades': performance.get('total_trades', 0),
        'pnl_total': pnl_data.get('PnL (total)', 0),
        'win_rate': pnl_data.get('Win Rate', 0),
        'expectancy': pnl_data.get('Expectancy', 0),
        'max_winner': pnl_data.get('Max Winner', 0),
        'avg_winner': pnl_data.get('Avg Winner', 0),
        'min_winner': pnl_data.get('Min Winner', 0),
        'max_loser': pnl_data.get('Max Loser', 0),
        'avg_loser': pnl_data.get('Avg Loser', 0),
        'min_loser': pnl_data.get('Min Loser', 0),
        'sharpe_ratio': returns_data.get('Sharpe Ratio (252 days)', 0),
        'profit_factor': returns_data.get('Profit Factor', 0),
    }

    return result

def main():
    print("=" * 100)
    print("交易案例分析")
    print("=" * 100)

    # 定义三个时期的结果文件
    periods = [
        ('2022-2024初', '/home/yixian/Projects/nautilus-practice/output/backtest/result/KeltnerRSBreakoutStrategy_2026-02-26_10-39-45.json'),
        ('2024年', '/home/yixian/Projects/nautilus-practice/output/backtest/result/KeltnerRSBreakoutStrategy_2026-02-26_10-49-40.json'),
        ('2025-2026', '/home/yixian/Projects/nautilus-practice/output/backtest/result/KeltnerRSBreakoutStrategy_2026-02-26_10-34-01.json'),
    ]

    results = []
    for period_name, file_path in periods:
        try:
            result = analyze_period(file_path, period_name)
            results.append(result)
        except Exception as e:
            print(f"错误分析 {period_name}: {e}")

    # 显示对比表格
    print(f"\n{'指标':<25} {'2022-2024初':<20} {'2024年':<20} {'2025-2026':<20}")
    print("-" * 100)

    if len(results) == 3:
        baseline, golden, failure = results

        print(f"{'总交易次数':<25} {baseline['total_trades']:>18} {golden['total_trades']:>18} {failure['total_trades']:>18}")
        print(f"{'总PnL (USDT)':<25} {baseline['pnl_total']:>18.2f} {golden['pnl_total']:>18.2f} {failure['pnl_total']:>18.2f}")
        print(f"{'胜率':<25} {baseline['win_rate']*100:>17.1f}% {golden['win_rate']*100:>17.1f}% {failure['win_rate']*100:>17.1f}%")
        print(f"{'期望值 (USDT/笔)':<25} {baseline['expectancy']:>18.2f} {golden['expectancy']:>18.2f} {failure['expectancy']:>18.2f}")
        print(f"{'Sharpe Ratio':<25} {baseline['sharpe_ratio']:>18.2f} {golden['sharpe_ratio']:>18.2f} {failure['sharpe_ratio']:>18.2f}")
        print(f"{'Profit Factor':<25} {baseline['profit_factor']:>18.2f} {golden['profit_factor']:>18.2f} {failure['profit_factor']:>18.2f}")
        print()
        print(f"{'最大盈利 (USDT)':<25} {baseline['max_winner']:>18.2f} {golden['max_winner']:>18.2f} {failure['max_winner']:>18.2f}")
        print(f"{'平均盈利 (USDT)':<25} {baseline['avg_winner']:>18.2f} {golden['avg_winner']:>18.2f} {failure['avg_winner']:>18.2f}")
        print(f"{'最小盈利 (USDT)':<25} {baseline['min_winner']:>18.2f} {golden['min_winner']:>18.2f} {failure['min_winner']:>18.2f}")
        print()
        print(f"{'最大亏损 (USDT)':<25} {baseline['max_loser']:>18.2f} {golden['max_loser']:>18.2f} {failure['max_loser']:>18.2f}")
        print(f"{'平均亏损 (USDT)':<25} {baseline['avg_loser']:>18.2f} {golden['avg_loser']:>18.2f} {failure['avg_loser']:>18.2f}")
        print(f"{'最小亏损 (USDT)':<25} {baseline['min_loser']:>18.2f} {golden['min_loser']:>18.2f} {failure['min_loser']:>18.2f}")

        print("\n" + "=" * 100)
        print("关键发现")
        print("=" * 100)

        print("\n2024年交易特征（黄金年份）：")
        print(f"  ✓ 超高胜率：{golden['win_rate']*100:.1f}%（远高于基准期的{baseline['win_rate']*100:.1f}%）")
        print(f"  ✓ 极高期望值：{golden['expectancy']:.2f} USDT/笔（基准期仅{baseline['expectancy']:.2f}）")
        print(f"  ✓ 优秀盈亏比：平均盈利{golden['avg_winner']:.2f} vs 平均亏损{abs(golden['avg_loser']):.2f}")
        print(f"  ✓ 大赢家：最大单笔盈利{golden['max_winner']:.2f} USDT")
        print(f"  ✓ Profit Factor：{golden['profit_factor']:.2f}（远超1.0的盈利门槛）")

        print("\n2025-2026年交易特征（失效期）：")
        print(f"  ✗ 胜率崩溃：{failure['win_rate']*100:.1f}%（从2024年的{golden['win_rate']*100:.1f}%暴跌）")
        print(f"  ✗ 负期望值：{failure['expectancy']:.2f} USDT/笔（每笔交易预期亏损）")
        print(f"  ✗ 盈亏比恶化：平均盈利{failure['avg_winner']:.2f} vs 平均亏损{abs(failure['avg_loser']):.2f}")
        print(f"  ✗ 交易频率下降：仅{failure['total_trades']}笔（2024年有{golden['total_trades']}笔）")
        print(f"  ✗ Profit Factor：{failure['profit_factor']:.2f}（远低于1.0，系统性亏损）")

        print("\n交易质量对比：")
        win_rate_drop = (golden['win_rate'] - failure['win_rate']) / golden['win_rate'] * 100
        expectancy_drop = (golden['expectancy'] - failure['expectancy']) / golden['expectancy'] * 100
        print(f"  → 胜率下降：{win_rate_drop:.1f}%")
        print(f"  → 期望值下降：{expectancy_drop:.1f}%")
        print(f"  → 2024年的成功不可复制，市场环境是关键因素")

        print("\n过滤器效果推测：")
        trade_freq_2024 = golden['total_trades'] / 366  # 每天交易频率
        trade_freq_2025 = failure['total_trades'] / 365
        print(f"  → 2024年交易频率：{trade_freq_2024:.3f} 笔/天")
        print(f"  → 2025-2026交易频率：{trade_freq_2025:.3f} 笔/天")
        print(f"  → 频率下降：{(1 - trade_freq_2025/trade_freq_2024)*100:.1f}%")
        print(f"  → 可能原因：过滤器在低波动环境下过度拦截信号")

if __name__ == '__main__':
    main()
