#!/usr/bin/env python
"""
Keltner RS Breakout 策略参数优化 - 阶段 1

快速验证阶段：测试 keltner_trigger_multiplier 和 deviation_threshold 的组合

使用方法：
    uv run python scripts/optimize_keltner_stage1.py
    uv run python scripts/optimize_keltner_stage1.py --parallel --workers 3
"""

import argparse
import itertools
import json
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml


def run_single_backtest(params: dict, config_path: Path, test_id: int) -> dict:
    """
    运行单次回测

    Args:
        params: 参数字典
        config_path: 配置文件路径
        test_id: 测试编号

    Returns:
        包含参数和结果的字典
    """
    # 备份原始配置
    backup_path = config_path.with_suffix('.yaml.backup_optimization')
    with open(config_path, 'r') as f:
        original_config = yaml.safe_load(f)

    with open(backup_path, 'w') as f:
        yaml.dump(original_config, f)

    try:
        print(f"[{test_id}/9] 测试参数: {params}")

        # 修改配置文件
        modified_config = original_config.copy()
        modified_config['parameters'].update(params)

        with open(config_path, 'w') as f:
            yaml.dump(modified_config, f)

        # 运行回测
        start_time = time.time()
        result = subprocess.run(
            ['uv', 'run', 'python', 'main.py', 'backtest', '--type', 'high'],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=Path(__file__).parent.parent
        )
        elapsed_time = time.time() - start_time

        # 解析结果
        if result.returncode == 0:
            # 从最新的结果文件读取
            result_dir = Path(__file__).parent.parent / 'output' / 'backtest' / 'result'
            result_files = sorted(result_dir.glob('KeltnerRSBreakoutStrategy_*.json'), key=lambda x: x.stat().st_mtime)

            if result_files:
                with open(result_files[-1], 'r') as f:
                    backtest_result = json.load(f)

                pnl_data = backtest_result['pnl']['USDT']
                returns_data = backtest_result['returns']

                # 安全处理 None 值
                avg_winner = pnl_data.get('Avg Winner') or 0
                avg_loser = pnl_data.get('Avg Loser') or 0
                profit_loss_ratio = abs(avg_winner / avg_loser) if avg_loser != 0 else 0

                return {
                    'test_id': test_id,
                    'keltner_trigger_multiplier': params['keltner_trigger_multiplier'],
                    'deviation_threshold': params['deviation_threshold'],
                    'sharpe_ratio': returns_data.get('Sharpe Ratio (252 days)') or 0,
                    'sortino_ratio': returns_data.get('Sortino Ratio (252 days)') or 0,
                    'total_trades': backtest_result['summary']['total_positions'],
                    'win_rate': pnl_data.get('Win Rate') or 0,
                    'expectancy': pnl_data.get('Expectancy') or 0,
                    'profit_factor': returns_data.get('Profit Factor') or 0,
                    'total_pnl': pnl_data['PnL (total)'],
                    'total_pnl_pct': pnl_data['PnL% (total)'],
                    'avg_winner': avg_winner,
                    'avg_loser': avg_loser,
                    'profit_loss_ratio': profit_loss_ratio,
                    'elapsed_time': elapsed_time,
                    'status': 'success'
                }

        return {
            'test_id': test_id,
            **params,
            'status': 'failed',
            'error': result.stderr[:200] if result.stderr else 'Unknown error',
            'elapsed_time': elapsed_time
        }

    except subprocess.TimeoutExpired:
        return {
            'test_id': test_id,
            **params,
            'status': 'timeout',
            'error': 'Backtest timeout after 300s'
        }
    except Exception as e:
        return {
            'test_id': test_id,
            **params,
            'status': 'error',
            'error': str(e)[:200]
        }
    finally:
        # 恢复原始配置
        if backup_path.exists():
            with open(backup_path, 'r') as f:
                original = yaml.safe_load(f)
            with open(config_path, 'w') as f:
                yaml.dump(original, f)


def run_parameter_sweep(
    param_grid: dict,
    parallel: bool = False,
    max_workers: int = 3
) -> pd.DataFrame:
    """执行参数网格搜索"""

    config_path = Path(__file__).parent.parent / 'config' / 'strategies' / 'keltner_rs_breakout.yaml'

    # 生成所有参数组合
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(itertools.product(*param_values))

    print(f"\n{'='*70}")
    print(f"阶段 1: 快速验证")
    print(f"{'='*70}")
    print(f"参数组合数: {len(combinations)}")
    print(f"预计耗时: {len(combinations) * 2} 分钟 (假设每次 2 分钟)")
    print(f"并行执行: {'是' if parallel else '否'} ({max_workers} 进程)" if parallel else "")
    print(f"{'='*70}\n")

    results = []

    if parallel:
        print(f"使用 {max_workers} 个并行进程\n")
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    run_single_backtest,
                    dict(zip(param_names, combo)),
                    config_path,
                    i + 1
                ): i for i, combo in enumerate(combinations)
            }

            for future in as_completed(futures):
                result = future.result()
                results.append(result)

                if result['status'] == 'success':
                    print(f"✅ [{result['test_id']}/9] 完成 - Sharpe: {result['sharpe_ratio']:.3f}, "
                          f"Trades: {result['total_trades']}, Win Rate: {result['win_rate']:.2%}")
                else:
                    print(f"❌ [{result['test_id']}/9] 失败 - {result['status']}")
    else:
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            result = run_single_backtest(params, config_path, i + 1)
            results.append(result)

            if result['status'] == 'success':
                print(f"✅ [{i+1}/9] 完成 - Sharpe: {result['sharpe_ratio']:.3f}, "
                      f"Trades: {result['total_trades']}, Win Rate: {result['win_rate']:.2%}\n")
            else:
                print(f"❌ [{i+1}/9] 失败 - {result['status']}\n")

    # 转换为 DataFrame
    df = pd.DataFrame(results)

    # 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent / 'output' / 'optimization'
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f'stage1_results_{timestamp}.csv'
    df.to_csv(output_path, index=False)

    print(f"\n{'='*70}")
    print(f"结果已保存至: {output_path}")
    print(f"{'='*70}\n")

    return df


def analyze_results(df: pd.DataFrame):
    """分析优化结果"""

    print("\n" + "="*70)
    print("阶段 1 优化结果分析")
    print("="*70)

    # 过滤成功的回测
    df_success = df[df['status'] == 'success'].copy()

    if len(df_success) == 0:
        print("⚠️  警告：没有成功的回测结果")
        return

    print(f"\n成功回测: {len(df_success)}/{len(df)} 组\n")

    # 按 Sharpe Ratio 排序
    df_success['sharpe_ratio'] = pd.to_numeric(df_success['sharpe_ratio'], errors='coerce')
    df_sorted = df_success.sort_values('sharpe_ratio', ascending=False)

    print("Top 5 参数组合（按 Sharpe Ratio 排序）:")
    print("-"*70)
    display_cols = [
        'keltner_trigger_multiplier',
        'deviation_threshold',
        'sharpe_ratio',
        'total_trades',
        'win_rate',
        'profit_loss_ratio',
        'total_pnl_pct'
    ]
    print(df_sorted[display_cols].head(5).to_string(index=False))
    print()

    # 基线对比
    baseline = {
        'keltner_trigger_multiplier': 2.8,
        'deviation_threshold': 0.45,
        'sharpe_ratio': 0.67,
        'total_trades': 55,
        'win_rate': 0.41
    }

    best = df_sorted.iloc[0]

    print("="*70)
    print("最优参数 vs 基线对比")
    print("="*70)
    print(f"{'指标':<30} {'基线':<15} {'最优':<15} {'变化':<15}")
    print("-"*70)
    print(f"{'keltner_trigger_multiplier':<30} {baseline['keltner_trigger_multiplier']:<15.2f} {best['keltner_trigger_multiplier']:<15.2f} {best['keltner_trigger_multiplier'] - baseline['keltner_trigger_multiplier']:+.2f}")
    print(f"{'deviation_threshold':<30} {baseline['deviation_threshold']:<15.2f} {best['deviation_threshold']:<15.2f} {best['deviation_threshold'] - baseline['deviation_threshold']:+.2f}")
    print(f"{'Sharpe Ratio':<30} {baseline['sharpe_ratio']:<15.3f} {best['sharpe_ratio']:<15.3f} {(best['sharpe_ratio'] - baseline['sharpe_ratio']) / baseline['sharpe_ratio'] * 100:+.1f}%")
    print(f"{'交易次数':<30} {baseline['total_trades']:<15.0f} {best['total_trades']:<15.0f} {(best['total_trades'] - baseline['total_trades']) / baseline['total_trades'] * 100:+.1f}%")
    print(f"{'胜率':<30} {baseline['win_rate']:<15.2%} {best['win_rate']:<15.2%} {(best['win_rate'] - baseline['win_rate']) * 100:+.1f}pp")
    print(f"{'盈亏比':<30} {'1.68':<15} {best['profit_loss_ratio']:<15.2f} {(best['profit_loss_ratio'] - 1.68) / 1.68 * 100:+.1f}%")
    print()

    # 参数敏感度分析
    print("="*70)
    print("参数敏感度分析")
    print("="*70)

    # keltner_trigger_multiplier 敏感度
    print("\nkeltner_trigger_multiplier 影响:")
    keltner_grouped = df_success.groupby('keltner_trigger_multiplier').agg({
        'sharpe_ratio': ['mean', 'std'],
        'total_trades': 'mean',
        'win_rate': 'mean'
    }).round(3)
    print(keltner_grouped)

    # deviation_threshold 敏感度
    print("\ndeviation_threshold 影响:")
    deviation_grouped = df_success.groupby('deviation_threshold').agg({
        'sharpe_ratio': ['mean', 'std'],
        'total_trades': 'mean',
        'win_rate': 'mean'
    }).round(3)
    print(deviation_grouped)

    # 保存最优参数
    best_params = {
        'stage': 1,
        'timestamp': datetime.now().isoformat(),
        'parameters': {
            'keltner_trigger_multiplier': float(best['keltner_trigger_multiplier']),
            'deviation_threshold': float(best['deviation_threshold'])
        },
        'metrics': {
            'sharpe_ratio': float(best['sharpe_ratio']),
            'sortino_ratio': float(best['sortino_ratio']),
            'total_trades': int(best['total_trades']),
            'win_rate': float(best['win_rate']),
            'profit_loss_ratio': float(best['profit_loss_ratio']),
            'total_pnl_pct': float(best['total_pnl_pct']),
            'expectancy': float(best['expectancy'])
        },
        'baseline_comparison': {
            'sharpe_improvement': f"{(best['sharpe_ratio'] - baseline['sharpe_ratio']) / baseline['sharpe_ratio'] * 100:+.1f}%",
            'trades_change': f"{(best['total_trades'] - baseline['total_trades']) / baseline['total_trades'] * 100:+.1f}%",
            'win_rate_change': f"{(best['win_rate'] - baseline['win_rate']) * 100:+.1f}pp"
        }
    }

    output_dir = Path(__file__).parent.parent / 'output' / 'optimization'
    best_params_path = output_dir / 'stage1_best_parameters.json'

    with open(best_params_path, 'w') as f:
        json.dump(best_params, f, indent=2)

    print(f"\n最优参数已保存至: {best_params_path}")
    print("="*70)


def main():
    parser = argparse.ArgumentParser(description='Keltner RS Breakout 策略参数优化 - 阶段 1')
    parser.add_argument('--parallel', action='store_true',
                        help='启用并行执行')
    parser.add_argument('--workers', type=int, default=3,
                        help='并行进程数 (默认: 3)')

    args = parser.parse_args()

    # 阶段 1 参数网格（基于 analyst 建议）
    param_grid = {
        'keltner_trigger_multiplier': [2.2, 2.4, 2.6],
        'deviation_threshold': [0.35, 0.38, 0.42]
    }

    print("\n" + "="*70)
    print("Keltner RS Breakout 策略参数优化")
    print("阶段 1: 快速验证")
    print("="*70)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # 运行优化
    start_time = time.time()
    df = run_parameter_sweep(param_grid, parallel=args.parallel, max_workers=args.workers)
    total_time = time.time() - start_time

    # 分析结果
    analyze_results(df)

    print(f"\n总耗时: {total_time / 60:.1f} 分钟")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)


if __name__ == "__main__":
    main()
