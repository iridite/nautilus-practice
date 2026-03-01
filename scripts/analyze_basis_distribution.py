#!/usr/bin/env python3
"""
分析资金费率套利策略回测期间的基差和资金费率数据

用途：
1. 计算基差的分位数分布
2. 找出满足开仓条件的时刻占比
3. 分析为什么策略没有产生交易
"""

import pandas as pd
from pathlib import Path
import sys


def load_spot_data(data_dir: Path, start_date: str, end_date: str) -> pd.DataFrame:
    """加载现货数据"""
    # 尝试加载所有1h数据文件
    spot_files = list((data_dir / "BTCUSDT").glob("binance-BTCUSDT-1h-*.csv"))

    if not spot_files:
        raise FileNotFoundError(f"No spot 1h data found in {data_dir / 'BTCUSDT'}")

    dfs = []
    for file in spot_files:
        df = pd.read_csv(file)
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]
    df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp'])
    df = df.rename(columns={'close': 'spot_close'})
    return df[['timestamp', 'spot_close']]


def load_perp_data(data_dir: Path, start_date: str, end_date: str) -> pd.DataFrame:
    """加载永续合约数据"""
    # 尝试加载所有1h数据文件
    perp_files = list((data_dir / "BTCUSDT-PERP").glob("binance-BTCUSDT-PERP-1h-*.csv"))

    if not perp_files:
        raise FileNotFoundError(f"No perp 1h data found in {data_dir / 'BTCUSDT-PERP'}")

    dfs = []
    for file in perp_files:
        df = pd.read_csv(file)
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]
    df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp'])
    df = df.rename(columns={'close': 'perp_close'})
    return df[['timestamp', 'perp_close']]


def load_funding_rate_data(data_dir: Path, start_date: str, end_date: str) -> pd.DataFrame:
    """加载资金费率数据"""
    # 尝试加载所有资金费率文件
    funding_files = list((data_dir / "BTCUSDT-PERP").glob("binance-BTCUSDT-PERP-funding_rate-*.csv"))

    if not funding_files:
        raise FileNotFoundError(f"No funding rate data found in {data_dir / 'BTCUSDT-PERP'}")

    dfs = []
    for file in funding_files:
        df = pd.read_csv(file)
        dfs.append(df)

    df = pd.concat(dfs, ignore_index=True)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]
    df = df.sort_values('timestamp').drop_duplicates(subset=['timestamp'])

    return df[['timestamp', 'funding_rate', 'funding_rate_annual']]


def analyze_basis_distribution(merged_df: pd.DataFrame, entry_threshold: float, exit_threshold: float):
    """分析基差分布"""
    print("\n" + "=" * 80)
    print("📊 基差分布分析")
    print("=" * 80)

    basis = merged_df['basis_pct']

    print(f"\n基差统计:")
    print(f"  数据点数: {len(basis)}")
    print(f"  平均值: {basis.mean():.4%}")
    print(f"  中位数: {basis.median():.4%}")
    print(f"  标准差: {basis.std():.4%}")
    print(f"  最小值: {basis.min():.4%}")
    print(f"  最大值: {basis.max():.4%}")

    print(f"\n基差分位数:")
    for q in [0.25, 0.50, 0.75, 0.90, 0.95, 0.99]:
        print(f"  {q*100:5.1f}%: {basis.quantile(q):.4%}")

    print(f"\n开仓条件分析:")
    print(f"  开仓阈值: {entry_threshold:.4%}")
    print(f"  平仓阈值: {exit_threshold:.4%}")

    above_entry = (basis >= entry_threshold).sum()
    above_exit = (basis >= exit_threshold).sum()

    print(f"  基差 >= 开仓阈值: {above_entry} / {len(basis)} ({above_entry/len(basis)*100:.2f}%)")
    print(f"  基差 >= 平仓阈值: {above_exit} / {len(basis)} ({above_exit/len(basis)*100:.2f}%)")

    if above_entry > 0:
        print(f"\n✅ 存在满足基差条件的时刻")
        print(f"   最早时刻: {merged_df[basis >= entry_threshold]['timestamp'].min()}")
        print(f"   最晚时刻: {merged_df[basis >= entry_threshold]['timestamp'].max()}")
    else:
        print(f"\n❌ 整个回测期间基差从未达到开仓阈值")
        print(f"   建议降低 entry_basis_pct 到: {basis.quantile(0.95):.4%} (95分位数)")


def analyze_funding_rate(merged_df: pd.DataFrame, min_funding_annual: float):
    """分析资金费率"""
    print("\n" + "=" * 80)
    print("💰 资金费率分析")
    print("=" * 80)

    funding = merged_df['funding_rate_annual'].dropna()

    print(f"\n资金费率统计:")
    print(f"  数据点数: {len(funding)}")
    print(f"  平均年化: {funding.mean():.2f}%")
    print(f"  中位数: {funding.median():.2f}%")
    print(f"  标准差: {funding.std():.2f}%")
    print(f"  最小值: {funding.min():.2f}%")
    print(f"  最大值: {funding.max():.2f}%")

    print(f"\n资金费率分位数:")
    for q in [0.25, 0.50, 0.75, 0.90, 0.95]:
        print(f"  {q*100:5.1f}%: {funding.quantile(q):.2f}%")

    print(f"\n开仓条件分析:")
    print(f"  最小资金费率阈值: {min_funding_annual:.2f}%")

    above_min = (funding >= min_funding_annual).sum()
    print(f"  资金费率 >= 阈值: {above_min} / {len(funding)} ({above_min/len(funding)*100:.2f}%)")

    if above_min == 0:
        print(f"\n❌ 整个回测期间资金费率从未达到最小阈值")
        print(f"   建议降低 min_funding_rate_annual 到: {funding.quantile(0.50):.2f}% (中位数)")


def analyze_combined_conditions(merged_df: pd.DataFrame, entry_basis: float, min_funding: float):
    """分析同时满足基差和资金费率条件的时刻"""
    print("\n" + "=" * 80)
    print("🎯 组合条件分析")
    print("=" * 80)

    # 前向填充资金费率（资金费率每8小时更新一次）
    merged_df['funding_rate_annual_ffill'] = merged_df['funding_rate_annual'].fillna(method='ffill')

    basis_ok = merged_df['basis_pct'] >= entry_basis
    funding_ok = merged_df['funding_rate_annual_ffill'] >= min_funding
    both_ok = basis_ok & funding_ok

    print(f"\n条件满足情况:")
    print(f"  仅基差满足: {basis_ok.sum()} / {len(merged_df)} ({basis_ok.sum()/len(merged_df)*100:.2f}%)")
    print(f"  仅资金费率满足: {funding_ok.sum()} / {len(merged_df)} ({funding_ok.sum()/len(merged_df)*100:.2f}%)")
    print(f"  两者都满足: {both_ok.sum()} / {len(merged_df)} ({both_ok.sum()/len(merged_df)*100:.2f}%)")

    if both_ok.sum() > 0:
        print(f"\n✅ 存在同时满足两个条件的时刻")
        opportunities = merged_df[both_ok][['timestamp', 'basis_pct', 'funding_rate_annual_ffill']]
        print(f"\n前 10 个机会:")
        print(opportunities.head(10).to_string(index=False))
    else:
        print(f"\n❌ 整个回测期间从未同时满足基差和资金费率条件")

        # 分析哪个条件更严格
        if basis_ok.sum() == 0:
            print(f"   主要瓶颈: 基差条件过严")
        elif funding_ok.sum() == 0:
            print(f"   主要瓶颈: 资金费率条件过严")
        else:
            print(f"   两个条件都过严，但错开了时间")


def main():
    # 配置
    data_dir = Path("data/raw")
    start_date = "2024-01-01"
    end_date = "2024-12-31"

    # 当前策略参数
    entry_basis_pct = 0.0008  # 0.08%
    exit_basis_pct = 0.0002   # 0.02%
    min_funding_rate_annual = 12.0  # 12%

    print("=" * 80)
    print("资金费率套利策略 - 基差与资金费率数据分析")
    print("=" * 80)
    print(f"\n回测期间: {start_date} ~ {end_date}")
    print(f"当前参数:")
    print(f"  entry_basis_pct: {entry_basis_pct:.4%}")
    print(f"  exit_basis_pct: {exit_basis_pct:.4%}")
    print(f"  min_funding_rate_annual: {min_funding_rate_annual:.2f}%")

    try:
        # 加载数据
        print(f"\n📥 加载数据...")
        spot_df = load_spot_data(data_dir, start_date, end_date)
        perp_df = load_perp_data(data_dir, start_date, end_date)
        funding_df = load_funding_rate_data(data_dir, start_date, end_date)

        print(f"  现货数据: {len(spot_df)} 条")
        print(f"  永续数据: {len(perp_df)} 条")
        print(f"  资金费率: {len(funding_df)} 条")

        # 合并数据
        merged_df = spot_df.merge(perp_df, on='timestamp', how='inner')
        merged_df = merged_df.merge(funding_df, on='timestamp', how='left')

        # 计算基差
        merged_df['basis_pct'] = (merged_df['perp_close'] - merged_df['spot_close']) / merged_df['spot_close']

        print(f"  合并后数据: {len(merged_df)} 条")

        # 分析
        analyze_basis_distribution(merged_df, entry_basis_pct, exit_basis_pct)
        analyze_funding_rate(merged_df, min_funding_rate_annual)
        analyze_combined_conditions(merged_df, entry_basis_pct, min_funding_rate_annual)

        print("\n" + "=" * 80)
        print("✅ 分析完成")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
