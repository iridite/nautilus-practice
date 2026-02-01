"""
OI Divergence 策略参数优化脚本

使用方法：
    uv run python scripts/optimize_parameters.py --stage 1
    uv run python scripts/optimize_parameters.py --stage 2 --parallel
"""

import argparse
import itertools
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yaml


def load_base_config(config_path: str = "config/yaml/strategies/oi_divergence.yaml") -> dict:
    """加载基础配置"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def run_single_backtest(params: dict, config_template: dict) -> dict:
    """
    运行单次回测

    注意：此函数需要在子进程中执行，避免NautilusTrader状态污染
    """
    import subprocess
    import tempfile

    # 创建临时配置文件
    config = config_template.copy()
    config['parameters'].update(params)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config, f)
        temp_config_path = f.name

    try:
        # 运行回测
        result = subprocess.run(
            ['uv', 'run', 'main.py', 'backtest', '--type', 'high', '--config', temp_config_path],
            capture_output=True,
            text=True,
            timeout=300
        )

        # 解析结果
        if result.returncode == 0:
            # 从输出中提取指标

            # 简化版：从最后的JSON结果文件读取
            result_files = sorted(Path('output/backtest/result').glob('*.json'))
            if result_files:
                with open(result_files[-1], 'r') as f:
                    backtest_result = json.load(f)

                return {
                    **params,
                    'sharpe_ratio': backtest_result['returns'].get('Sharpe Ratio (252 days)'),
                    'total_trades': backtest_result['summary']['total_orders'],
                    'total_pnl': backtest_result['pnl']['USDT']['PnL (total)'],
                    'win_rate': backtest_result['pnl']['USDT'].get('Win Rate'),
                    'status': 'success'
                }

        return {**params, 'status': 'failed', 'error': result.stderr[:200]}

    except Exception as e:
        return {**params, 'status': 'error', 'error': str(e)[:200]}

    finally:
        Path(temp_config_path).unlink(missing_ok=True)


def run_parameter_sweep(
    param_grid: Dict[str, List],
    parallel: bool = False,
    max_workers: int = 4
) -> pd.DataFrame:
    """执行参数网格搜索"""

    base_config = load_base_config()

    # 生成所有参数组合
    param_names = list(param_grid.keys())
    param_values = list(param_grid.values())
    combinations = list(itertools.product(*param_values))

    print(f"总测试组合数: {len(combinations)}")

    results = []

    if parallel:
        print(f"使用 {max_workers} 个并行进程")
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(run_single_backtest, dict(zip(param_names, combo)), base_config)
                for combo in combinations
            ]

            for i, future in enumerate(futures):
                result = future.result()
                results.append(result)
                print(f"[{i+1}/{len(combinations)}] 完成: {result.get('status')}")
    else:
        for i, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            print(f"\n[{i+1}/{len(combinations)}] 测试: {params}")

            result = run_single_backtest(params, base_config)
            results.append(result)

    df = pd.DataFrame(results)

    # 保存结果
    output_path = Path('output/parameter_optimization_results.csv')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"\n结果已保存至: {output_path}")

    return df


def analyze_results(df: pd.DataFrame):
    """分析优化结果"""

    print("\n" + "="*70)
    print("参数优化结果分析")
    print("="*70)

    # 过滤成功的回测
    df_success = df[df['status'] == 'success'].copy()

    if len(df_success) == 0:
        print("警告：没有成功的回测结果")
        return

    # 按Sharpe排序
    df_success['sharpe_ratio'] = pd.to_numeric(df_success['sharpe_ratio'], errors='coerce')
    df_sorted = df_success.sort_values('sharpe_ratio', ascending=False)

    print("\nTop 5 参数组合（按Sharpe排序）:")
    print(df_sorted.head(5)[['oi_decline_threshold', 'funding_rate_threshold_annual',
                              'sharpe_ratio', 'total_trades', 'total_pnl']])

    # 鲁棒性分析
    if 'oi_decline_threshold' in df_success.columns:
        print("\n" + "="*70)
        print("OI阈值鲁棒性分析")
        print("="*70)

        grouped = df_success.groupby('oi_decline_threshold').agg({
            'sharpe_ratio': ['mean', 'std', 'count'],
            'total_trades': 'mean'
        })

        print(grouped)

    # 保存最优参数
    best = df_sorted.iloc[0]
    best_params = {
        'oi_decline_threshold': best['oi_decline_threshold'],
        'funding_rate_threshold_annual': best['funding_rate_threshold_annual'],
        'sharpe_ratio': best['sharpe_ratio'],
        'total_trades': best['total_trades']
    }

    with open('output/best_parameters.json', 'w') as f:
        json.dump(best_params, f, indent=2)

    print("\n最优参数已保存至: output/best_parameters.json")


def main():
    parser = argparse.ArgumentParser(description='OI Divergence 策略参数优化')
    parser.add_argument('--stage', type=int, default=1, choices=[1, 2, 3],
                        help='优化阶段: 1=单参数, 2=双参数, 3=全局')
    parser.add_argument('--parallel', action='store_true',
                        help='启用并行执行')
    parser.add_argument('--workers', type=int, default=4,
                        help='并行进程数')

    args = parser.parse_args()

    # 定义参数网格
    if args.stage == 1:
        # 阶段1：单参数敏感性分析
        param_grid = {
            'oi_decline_threshold': [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05],
            'oi_lookback': [12],
            'funding_rate_threshold_annual': [30.0],
            'lookback_bars': [48],
            'atr_stop_multiplier': [2.0]
        }
    elif args.stage == 2:
        # 阶段2：双参数交互分析
        param_grid = {
            'oi_decline_threshold': [0.01, 0.02, 0.03, 0.04, 0.05],
            'oi_lookback': [12],
            'funding_rate_threshold_annual': [10.0, 15.0, 20.0, 25.0, 30.0],
            'lookback_bars': [48],
            'atr_stop_multiplier': [2.0]
        }
    else:
        # 阶段3：全局优化
        param_grid = {
            'oi_decline_threshold': [0.01, 0.02, 0.03, 0.05],
            'oi_lookback': [6, 12, 24],
            'funding_rate_threshold_annual': [10.0, 15.0, 20.0, 30.0],
            'lookback_bars': [24, 48, 96],
            'atr_stop_multiplier': [1.5, 2.0, 2.5, 3.0]
        }

    print(f"开始阶段 {args.stage} 参数优化...")

    # 运行优化
    df = run_parameter_sweep(param_grid, parallel=args.parallel, max_workers=args.workers)

    # 分析结果
    analyze_results(df)


if __name__ == "__main__":
    main()
