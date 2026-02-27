#!/usr/bin/env python3
"""
参数优化快速验证测试脚本

自动化执行 9 组参数组合的回测测试
"""

import subprocess
import yaml
import json
import csv
from pathlib import Path
from datetime import datetime
import shutil

# 配置路径
CONFIG_PATH = Path("/home/yixian/Projects/nautilus-practice/config/strategies/keltner_rs_breakout.yaml")
BACKUP_PATH = CONFIG_PATH.with_suffix(".yaml.backup_optimization")
OUTPUT_DIR = Path("/home/yixian/Projects/nautilus-practice/output/optimization")
RESULTS_CSV = OUTPUT_DIR / "quick_test_results.csv"

# 测试参数组合
KELTNER_MULTIPLIERS = [2.2, 2.4, 2.6]
DEVIATION_THRESHOLDS = [0.35, 0.38, 0.42]

def backup_config():
    """备份原始配置"""
    shutil.copy(CONFIG_PATH, BACKUP_PATH)
    print(f"✓ 已备份配置到: {BACKUP_PATH}")

def restore_config():
    """恢复原始配置"""
    if BACKUP_PATH.exists():
        shutil.copy(BACKUP_PATH, CONFIG_PATH)
        print(f"✓ 已恢复原始配置")

def update_config(keltner_multiplier, deviation_threshold):
    """更新配置文件中的参数"""
    with open(CONFIG_PATH, 'r') as f:
        config = yaml.safe_load(f)

    config['parameters']['keltner_trigger_multiplier'] = keltner_multiplier
    config['parameters']['deviation_threshold'] = deviation_threshold

    with open(CONFIG_PATH, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

def run_backtest():
    """运行回测"""
    cmd = ["uv", "run", "python", "main.py", "backtest", "--type", "high"]
    result = subprocess.run(
        cmd,
        cwd="/home/yixian/Projects/nautilus-practice",
        capture_output=True,
        text=True
    )
    return result

def parse_results(stdout):
    """解析回测结果"""
    try:
        # 查找 JSON 输出
        lines = stdout.split('\n')
        for i, line in enumerate(lines):
            if '"total_pnl"' in line or '"net_profit"' in line:
                # 尝试解析 JSON
                json_start = i
                while json_start > 0 and lines[json_start].strip() != '{':
                    json_start -= 1

                json_end = i
                while json_end < len(lines) and lines[json_end].strip() != '}':
                    json_end += 1

                json_str = '\n'.join(lines[json_start:json_end+1])
                data = json.loads(json_str)

                return {
                    'net_profit': data.get('total_pnl', data.get('net_profit', 0)),
                    'total_trades': data.get('total_trades', 0),
                    'win_rate': data.get('win_rate', 0),
                    'sharpe_ratio': data.get('sharpe_ratio', 0),
                    'profit_factor': data.get('profit_factor', 0)
                }
    except Exception as e:
        print(f"  ⚠ 解析结果失败: {e}")

    return {
        'net_profit': 0,
        'total_trades': 0,
        'win_rate': 0,
        'sharpe_ratio': 0,
        'profit_factor': 0
    }

def main():
    print("=" * 60)
    print("参数优化快速验证测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试组合: {len(KELTNER_MULTIPLIERS)} × {len(DEVIATION_THRESHOLDS)} = {len(KELTNER_MULTIPLIERS) * len(DEVIATION_THRESHOLDS)} 组")
    print()

    # 备份配置
    backup_config()

    # 准备结果记录
    results = []

    try:
        # 执行测试
        test_num = 0
        total_tests = len(KELTNER_MULTIPLIERS) * len(DEVIATION_THRESHOLDS)

        for keltner in KELTNER_MULTIPLIERS:
            for deviation in DEVIATION_THRESHOLDS:
                test_num += 1
                print(f"[{test_num}/{total_tests}] 测试参数组合:")
                print(f"  keltner_trigger_multiplier: {keltner}")
                print(f"  deviation_threshold: {deviation}")

                # 更新配置
                update_config(keltner, deviation)

                # 运行回测
                print("  运行回测中...")
                result = run_backtest()

                # 解析结果
                metrics = parse_results(result.stdout)

                # 记录结果
                row = {
                    'test_num': test_num,
                    'keltner_trigger_multiplier': keltner,
                    'deviation_threshold': deviation,
                    'net_profit_usdt': metrics['net_profit'],
                    'total_trades': metrics['total_trades'],
                    'win_rate': metrics['win_rate'],
                    'sharpe_ratio': metrics['sharpe_ratio'],
                    'profit_factor': metrics['profit_factor']
                }
                results.append(row)

                print(f"  ✓ 净利润: {metrics['net_profit']:.2f} USDT")
                print(f"  ✓ 交易数: {metrics['total_trades']}")
                print(f"  ✓ 胜率: {metrics['win_rate']:.2%}")
                print(f"  ✓ 夏普: {metrics['sharpe_ratio']:.2f}")
                print(f"  ✓ 盈亏比: {metrics['profit_factor']:.2f}")
                print()

        # 保存结果到 CSV
        with open(RESULTS_CSV, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'test_num',
                'keltner_trigger_multiplier',
                'deviation_threshold',
                'net_profit_usdt',
                'total_trades',
                'win_rate',
                'sharpe_ratio',
                'profit_factor'
            ])
            writer.writeheader()
            writer.writerows(results)

        print("=" * 60)
        print(f"✓ 测试完成！结果已保存到: {RESULTS_CSV}")
        print("=" * 60)

        # 显示最佳结果
        if results:
            best = max(results, key=lambda x: x['net_profit_usdt'])
            print("\n最佳参数组合:")
            print(f"  keltner_trigger_multiplier: {best['keltner_trigger_multiplier']}")
            print(f"  deviation_threshold: {best['deviation_threshold']}")
            print(f"  净利润: {best['net_profit_usdt']:.2f} USDT")
            print(f"  交易数: {best['total_trades']}")
            print(f"  胜率: {best['win_rate']:.2%}")
            print(f"  夏普: {best['sharpe_ratio']:.2f}")
            print(f"  盈亏比: {best['profit_factor']:.2f}")

    finally:
        # 恢复原始配置
        restore_config()

if __name__ == "__main__":
    main()
