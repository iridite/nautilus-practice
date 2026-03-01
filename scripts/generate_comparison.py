"""
从已有的回测结果生成对比表格

用法:
    uv run python scripts/generate_comparison.py
"""

import json
from pathlib import Path

import pandas as pd


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    result_dir = project_root / "output/backtest/result"

    # 读取所有回测结果
    result_files = sorted(
        result_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True
    )

    # 按币种去重，保留每个币种最新的结果
    symbol_results = {}
    for result_file in result_files:
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                symbol = data.get("strategy_config", {}).get("symbols", ["Unknown"])[0]

                # 只保留每个币种最新的结果
                if symbol not in symbol_results:
                    data["symbol"] = symbol
                    symbol_results[symbol] = data
        except (json.JSONDecodeError, KeyError) as e:
            print(f"⚠️ 跳过损坏的文件: {result_file.name} ({e})")
            continue

    if len(symbol_results) < 1:
        print(f"❌ 没有找到回测结果")
        return 1

    results = list(symbol_results.values())

    # 只保留有交易的结果（过滤掉 Unknown 和无交易的币种）
    results = [
        r for r in results
        if r.get("performance", {}).get("total_orders", 0) > 0
        and r.get("symbol") != "Unknown"
    ]

    if len(results) < 1:
        print(f"❌ 没有找到有效的回测结果")
        return 1

    # 提取关键指标
    comparison_data = []
    for result in results:
        symbol = result.get("symbol", "Unknown")
        performance = result.get("performance", {})

        comparison_data.append(
            {
                "币种": symbol,
                "初始资金 (USDT)": 100000.0,
                "引擎 PnL (USDT)": round(performance.get("engine_pnl", 0), 2),
                "资金费率收益 (USDT)": round(performance.get("funding_collected", 0), 2),
                "真实 PnL (USDT)": round(performance.get("real_pnl", 0), 2),
                "收益率 (%)": round(performance.get("real_return_pct", 0), 2),
                "订单数": performance.get("total_orders", 0),
                "持仓数": performance.get("total_positions", 0),
            }
        )

    # 创建 DataFrame
    df = pd.DataFrame(comparison_data)

    # 按收益率排序
    df = df.sort_values("收益率 (%)", ascending=False)

    # 保存到 CSV
    output_file = project_root / "output/backtest/comparison.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_file, index=False, encoding="utf-8-sig")

    # 打印表格
    print(f"\n{'=' * 100}")
    print("📊 资金费率套利策略 - 2024 全年回测结果对比")
    print(f"{'=' * 100}\n")
    print(df.to_string(index=False))
    print(f"\n{'=' * 100}")
    print(f"✅ 对比表格已保存: {output_file}")
    print(f"{'=' * 100}\n")

    # 打印关键发现
    print("🔍 关键发现:")
    print(f"  • 最佳表现: {df.iloc[0]['币种']} (+{df.iloc[0]['收益率 (%)']}%)")
    print(f"  • 最差表现: {df.iloc[-1]['币种']} (+{df.iloc[-1]['收益率 (%)']}%)")
    print(
        f"  • 平均收益率: {df['收益率 (%)'].mean():.2f}%"
    )
    print(
        f"  • 总资金费率收益: {df['资金费率收益 (USDT)'].sum():.2f} USDT"
    )
    print()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
