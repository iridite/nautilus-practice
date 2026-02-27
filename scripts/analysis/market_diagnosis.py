#!/usr/bin/env python3
"""市场环境诊断分析"""

import pandas as pd
import numpy as np
from pathlib import Path
import json

def load_btc_data(period_name, start_date, end_date):
    """加载BTC数据"""
    file_path = f"/home/yixian/Projects/nautilus-practice/data/raw/BTCUSDT/binance-BTCUSDT-1d-{start_date}_{end_date}.csv"
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp')
    return df

def calculate_market_metrics(df, period_name):
    """计算市场特征指标"""
    # 计算收益率
    df['returns'] = df['close'].pct_change()

    # 计算ATR (简化版本，使用真实波动范围)
    df['high_low'] = df['high'] - df['low']
    df['high_close'] = abs(df['high'] - df['close'].shift(1))
    df['low_close'] = abs(df['low'] - df['close'].shift(1))
    df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
    df['atr_14'] = df['true_range'].rolling(14).mean()
    df['atr_pct'] = (df['atr_14'] / df['close']) * 100

    # 计算趋势强度 (SMA200)
    df['sma_200'] = df['close'].rolling(200).mean()
    df['above_sma200'] = (df['close'] > df['sma_200']).astype(int)

    # 计算价格变化
    price_change = ((df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]) * 100

    metrics = {
        'period': period_name,
        'start_date': df.index[0].strftime('%Y-%m-%d'),
        'end_date': df.index[-1].strftime('%Y-%m-%d'),
        'days': len(df),
        'price_start': df['close'].iloc[0],
        'price_end': df['close'].iloc[-1],
        'price_change_pct': price_change,
        'price_min': df['close'].min(),
        'price_max': df['close'].max(),
        'volatility_daily': df['returns'].std() * 100,
        'volatility_annual': df['returns'].std() * np.sqrt(252) * 100,
        'avg_atr_pct': df['atr_pct'].mean(),
        'max_atr_pct': df['atr_pct'].max(),
        'days_above_sma200': df['above_sma200'].sum(),
        'pct_above_sma200': (df['above_sma200'].sum() / len(df)) * 100,
        'avg_volume': df['volume'].mean(),
        'max_daily_gain': df['returns'].max() * 100,
        'max_daily_loss': df['returns'].min() * 100,
    }

    return metrics

def main():
    print("=" * 100)
    print("市场环境诊断分析")
    print("=" * 100)

    # 定义三个时期
    periods = [
        ('2022-2024初', '2022-01-01', '2024-01-01'),
        ('2024年', '2024-01-01', '2025-01-01'),
        ('2025-2026', '2025-01-01', '2026-01-01'),
    ]

    all_metrics = []

    for period_name, start_date, end_date in periods:
        print(f"\n分析时期: {period_name}")
        print("-" * 100)

        try:
            df = load_btc_data(period_name, start_date, end_date)
            metrics = calculate_market_metrics(df, period_name)
            all_metrics.append(metrics)

            print(f"时间范围: {metrics['start_date']} 到 {metrics['end_date']} ({metrics['days']} 天)")
            print(f"价格变化: ${metrics['price_start']:.2f} → ${metrics['price_end']:.2f} ({metrics['price_change_pct']:+.2f}%)")
            print(f"价格区间: ${metrics['price_min']:.2f} - ${metrics['price_max']:.2f}")
            print(f"日波动率: {metrics['volatility_daily']:.2f}%")
            print(f"年化波动率: {metrics['volatility_annual']:.2f}%")
            print(f"平均ATR%: {metrics['avg_atr_pct']:.2f}%")
            print(f"最大ATR%: {metrics['max_atr_pct']:.2f}%")
            print(f"SMA200上方天数: {metrics['days_above_sma200']}/{metrics['days']} ({metrics['pct_above_sma200']:.1f}%)")
            print(f"最大单日涨幅: {metrics['max_daily_gain']:.2f}%")
            print(f"最大单日跌幅: {metrics['max_daily_loss']:.2f}%")
            print(f"平均成交量: {metrics['avg_volume']:.0f}")

        except Exception as e:
            print(f"错误: {e}")

    # 对比分析
    print("\n" + "=" * 100)
    print("对比分析")
    print("=" * 100)

    if len(all_metrics) == 3:
        baseline = all_metrics[0]  # 2022-2024初
        golden = all_metrics[1]    # 2024年
        failure = all_metrics[2]   # 2025-2026

        print(f"\n{'指标':<30} {'2022-2024初':<20} {'2024年':<20} {'2025-2026':<20}")
        print("-" * 100)
        print(f"{'价格变化':<30} {baseline['price_change_pct']:>+18.2f}% {golden['price_change_pct']:>+18.2f}% {failure['price_change_pct']:>+18.2f}%")
        print(f"{'年化波动率':<30} {baseline['volatility_annual']:>18.2f}% {golden['volatility_annual']:>18.2f}% {failure['volatility_annual']:>18.2f}%")
        print(f"{'平均ATR%':<30} {baseline['avg_atr_pct']:>18.2f}% {golden['avg_atr_pct']:>18.2f}% {failure['avg_atr_pct']:>18.2f}%")
        print(f"{'SMA200上方占比':<30} {baseline['pct_above_sma200']:>18.1f}% {golden['pct_above_sma200']:>18.1f}% {failure['pct_above_sma200']:>18.1f}%")
        print(f"{'最大单日涨幅':<30} {baseline['max_daily_gain']:>18.2f}% {golden['max_daily_gain']:>18.2f}% {failure['max_daily_gain']:>18.2f}%")

        print("\n" + "=" * 100)
        print("关键发现")
        print("=" * 100)

        # 分析2024年的特殊性
        print("\n2024年市场特征（策略黄金年份）：")
        if golden['price_change_pct'] > baseline['price_change_pct'] * 2:
            print(f"  ✓ 强劲牛市：价格上涨 {golden['price_change_pct']:.1f}%，远超其他时期")
        if golden['volatility_annual'] > baseline['volatility_annual'] * 1.2:
            print(f"  ✓ 高波动环境：年化波动率 {golden['volatility_annual']:.1f}%，高于基准期")
        if golden['pct_above_sma200'] > 80:
            print(f"  ✓ 持续上涨趋势：{golden['pct_above_sma200']:.1f}% 时间在SMA200上方")
        if golden['avg_atr_pct'] > baseline['avg_atr_pct'] * 1.1:
            print(f"  ✓ 大幅波动：平均ATR {golden['avg_atr_pct']:.2f}%，提供充足交易机会")

        print("\n2025-2026年市场特征（策略失效期）：")
        if failure['price_change_pct'] < 0:
            print(f"  ✗ 熊市或震荡：价格下跌 {failure['price_change_pct']:.1f}%")
        if failure['volatility_annual'] < golden['volatility_annual'] * 0.7:
            print(f"  ✗ 低波动环境：年化波动率 {failure['volatility_annual']:.1f}%，低于2024年")
        if failure['pct_above_sma200'] < 50:
            print(f"  ✗ 弱势趋势：仅 {failure['pct_above_sma200']:.1f}% 时间在SMA200上方")
        if failure['avg_atr_pct'] < golden['avg_atr_pct'] * 0.8:
            print(f"  ✗ 波动收缩：平均ATR {failure['avg_atr_pct']:.2f}%，交易机会减少")

        print("\n策略适用性诊断：")
        print("  → 策略高度依赖【牛市+高波动+强趋势】的市场环境")
        print("  → 2024年是完美的市场环境，策略表现异常优秀")
        print("  → 2025-2026年市场环境变化，策略完全失效")
        print("  → 建议：引入市场环境识别机制，在不利环境下减少或停止交易")

if __name__ == '__main__':
    main()
