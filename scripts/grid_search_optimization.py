#!/usr/bin/env python
"""
参数网格搜索优化脚本
目标：通过调整 stop_loss_atr_multiplier 和 keltner_trigger_multiplier 提升盈亏比至 2.5+
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

import yaml

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def run_backtest_with_params(
    config_path: Path,
    stop_loss_atr: float,
    keltner_trigger: float,
    max_wick_ratio: float,
    test_id: int,
    total_tests: int,
) -> Dict:
    """运行单次回测"""
    # 备份原始配置
    backup_path = config_path.with_suffix(".yaml.backup_grid_search")
    with open(config_path, "r") as f:
        original_config = yaml.safe_load(f)

    with open(backup_path, "w") as f:
        yaml.dump(original_config, f)

    params = {
        "stop_loss_atr_multiplier": stop_loss_atr,
        "keltner_trigger_multiplier": keltner_trigger,
        "max_upper_wick_ratio": max_wick_ratio,
    }

    try:
        print(f"\n{'=' * 80}")
        print(f"[{test_id}/{total_tests}] 测试参数组合:")
        print(f"  stop_loss_atr_multiplier: {stop_loss_atr}")
        print(f"  keltner_trigger_multiplier: {keltner_trigger}")
        print(f"  max_upper_wick_ratio: {max_wick_ratio}")
        print(f"{'=' * 80}\n")

        # 修改配置文件
        modified_config = original_config.copy()
        modified_config["parameters"].update(params)

        with open(config_path, "w") as f:
            yaml.dump(modified_config, f)

        # 运行回测
        start_time = time.time()
        result = subprocess.run(
            ["uv", "run", "python", "main.py", "backtest", "--type", "high", "--skip-data-check"],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=Path(__file__).parent.parent,
        )
        elapsed_time = time.time() - start_time

        # 解析结果
        if result.returncode == 0:
            result_dir = Path(__file__).parent.parent / "output" / "backtest" / "result"
            result_files = sorted(
                result_dir.glob("KeltnerRSBreakoutStrategy_*.json"), key=lambda x: x.stat().st_mtime
            )

            if result_files:
                with open(result_files[-1], "r") as f:
                    backtest_result = json.load(f)

                pnl_data = backtest_result.get("pnl", {}).get("USDT", {})
                returns_data = backtest_result.get("returns", {})
                performance = backtest_result.get("performance", {})

                # 计算盈亏比
                avg_winner = pnl_data.get("Avg Winner") or 0
                avg_loser = abs(pnl_data.get("Avg Loser") or -1)
                payoff_ratio = avg_winner / avg_loser if avg_loser > 0 else 0

                return {
                    "params": params,
                    "success": True,
                    "pnl_total": pnl_data.get("PnL (total)", 0),
                    "pnl_pct": pnl_data.get("PnL% (total)", 0),
                    "win_rate": pnl_data.get("Win Rate", 0),
                    "avg_winner": avg_winner,
                    "avg_loser": -avg_loser,
                    "payoff_ratio": payoff_ratio,
                    "expectancy": pnl_data.get("Expectancy", 0),
                    "sharpe_ratio": returns_data.get("Sharpe Ratio (252 days)", 0),
                    "sortino_ratio": returns_data.get("Sortino Ratio (252 days)", 0),
                    "profit_factor": returns_data.get("Profit Factor", 0),
                    "total_trades": performance.get("total_trades", 0),
                    "elapsed_time": elapsed_time,
                }
            else:
                return {"params": params, "success": False, "error": "No result file found"}
        else:
            return {
                "params": params,
                "success": False,
                "error": f"Backtest failed: {result.stderr[:200]}",
            }

    except Exception as e:
        return {"params": params, "success": False, "error": str(e)}

    finally:
        # 恢复原始配置
        with open(backup_path, "r") as f:
            original_config = yaml.safe_load(f)
        with open(config_path, "w") as f:
            yaml.dump(original_config, f)
        backup_path.unlink()


def main():
    """主函数"""
    # 参数网格
    stop_loss_atr_values = [2.6, 3.0, 3.5]
    keltner_trigger_values = [2.2, 2.5, 2.8]
    max_wick_ratio = 0.35  # 固定值

    # 生成所有参数组合
    param_combinations = [
        (sl, kt, max_wick_ratio)
        for sl in stop_loss_atr_values
        for kt in keltner_trigger_values
    ]

    total_tests = len(param_combinations)
    print(f"\n🔍 开始网格搜索优化")
    print(f"📊 总共 {total_tests} 组参数组合")
    print(f"⏱️  预计耗时: {total_tests * 2} 分钟\n")

    # 配置文件路径
    config_path = Path(__file__).parent.parent / "config" / "strategies" / "keltner_rs_breakout.yaml"

    # 运行所有测试
    results = []
    for i, (sl, kt, mw) in enumerate(param_combinations, 1):
        result = run_backtest_with_params(config_path, sl, kt, mw, i, total_tests)
        results.append(result)

        if result["success"]:
            print(f"✅ 完成: PnL={result['pnl_pct']:.2f}%, Payoff={result['payoff_ratio']:.2f}, Sharpe={result['sharpe_ratio']:.3f}")
        else:
            print(f"❌ 失败: {result.get('error', 'Unknown error')}")

    # 过滤成功的结果
    successful_results = [r for r in results if r["success"]]

    if not successful_results:
        print("\n❌ 所有测试都失败了")
        return

    # 创建结果表格
    if not HAS_PANDAS:
        print("\n⚠️  pandas 未安装，使用简化输出")
        # 手动排序找最佳结果
        qualified = [r for r in successful_results if r["payoff_ratio"] > 2.5]
        if qualified:
            best = max(qualified, key=lambda x: x["sharpe_ratio"])
        else:
            best = max(successful_results, key=lambda x: x["sharpe_ratio"])
    else:
        import pandas as pd
        import pandas as pd
        df = pd.DataFrame(successful_results)

        # 保存完整结果
        output_dir = Path(__file__).parent.parent / "output" / "optimization"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = output_dir / f"grid_search_results_{timestamp}.csv"
        df.to_csv(csv_path, index=False)

        # 筛选符合条件的结果（Payoff Ratio > 2.5）
        qualified = df[df["payoff_ratio"] > 2.5]

    print(f"\n{'=' * 100}")
    print("📊 网格搜索结果汇总")
    print(f"{'=' * 100}\n")

    if len(qualified) > 0:
        # 按 Sharpe Ratio 排序
        best = qualified.sort_values("sharpe_ratio", ascending=False).iloc[0]

        print("🏆 最佳参数组合（Payoff Ratio > 2.5 且 Sharpe Ratio 最高）:")
        print(f"\n参数配置:")
        print(f"  stop_loss_atr_multiplier: {best['params']['stop_loss_atr_multiplier']}")
        print(f"  keltner_trigger_multiplier: {best['params']['keltner_trigger_multiplier']}")
        print(f"  max_upper_wick_ratio: {best['params']['max_upper_wick_ratio']}")
        print(f"\n绩效指标:")
        print(f"  PnL: {best['pnl_total']:.2f} USDT ({best['pnl_pct']:.2f}%)")
        print(f"  Win Rate: {best['win_rate'] * 100:.2f}%")
        print(f"  Total Trades: {int(best['total_trades'])}")
        print(f"  Avg Winner: {best['avg_winner']:.2f} USDT")
        print(f"  Avg Loser: {best['avg_loser']:.2f} USDT")
        print(f"  Payoff Ratio: {best['payoff_ratio']:.2f}")
        print(f"  Expectancy: {best['expectancy']:.4f}")
        print(f"  Sharpe Ratio: {best['sharpe_ratio']:.3f}")
        print(f"  Sortino Ratio: {best['sortino_ratio']:.3f}")
        print(f"  Profit Factor: {best['profit_factor']:.3f}")
    else:
        print("⚠️  没有参数组合达到 Payoff Ratio > 2.5 的目标")
        print("\n显示 Sharpe Ratio 最高的前 3 组:")

        top3 = df.sort_values("sharpe_ratio", ascending=False).head(3)
        for idx, row in top3.iterrows():
            print(f"\n#{idx + 1}:")
            print(f"  参数: SL={row['params']['stop_loss_atr_multiplier']}, KT={row['params']['keltner_trigger_multiplier']}")
            print(f"  PnL: {row['pnl_pct']:.2f}%, Payoff: {row['payoff_ratio']:.2f}, Sharpe: {row['sharpe_ratio']:.3f}")

    print(f"\n📁 完整结果已保存至: {csv_path}")
    print(f"{'=' * 100}\n")


if __name__ == "__main__":
    main()
