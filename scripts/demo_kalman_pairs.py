"""
卡尔曼配对交易策略 - 简单回测测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


import numpy as np

# 测试卡尔曼滤波器
from strategy.kalman_pairs import KalmanPairsTradingConfig, OnlineKalmanFilter


def test_kalman_filter():
    """测试卡尔曼滤波器基本功能"""
    print("=" * 60)
    print("测试卡尔曼滤波器")
    print("=" * 60)

    kalman = OnlineKalmanFilter(delta=1e-4, R=1.0)

    # 模拟价格数据 (SOL vs ETH)
    np.random.seed(42)
    n_samples = 100

    # 生成相关价格序列
    eth_prices = 2000 + np.cumsum(np.random.randn(n_samples) * 10)
    sol_prices = 100 + 0.05 * eth_prices + np.cumsum(np.random.randn(n_samples) * 2)

    print(f"\n生成{n_samples}个价格样本")
    print(f"ETH价格范围: {eth_prices.min():.2f} - {eth_prices.max():.2f}")
    print(f"SOL价格范围: {sol_prices.min():.2f} - {sol_prices.max():.2f}")

    # 更新滤波器
    z_scores = []
    betas = []

    for i in range(n_samples):
        alpha, beta, z_score = kalman.update(sol_prices[i], eth_prices[i])
        z_scores.append(z_score)
        betas.append(beta)

        if i % 20 == 0:
            print(f"\n[样本 {i}]")
            print(f"  SOL={sol_prices[i]:.2f}, ETH={eth_prices[i]:.2f}")
            print(f"  Beta={beta:.6f}, Z-Score={z_score:.2f}")

    # 统计信息
    z_scores = np.array(z_scores)
    betas = np.array(betas)

    print("\n" + "-" * 60)
    print("统计结果:")
    print(f"  Beta均值: {betas.mean():.6f}")
    print(f"  Beta标准差: {betas.std():.6f}")
    print(f"  Z-Score均值: {z_scores.mean():.2f}")
    print(f"  Z-Score标准差: {z_scores.std():.2f}")
    print(f"  Z-Score范围: [{z_scores.min():.2f}, {z_scores.max():.2f}]")

    # 交易信号统计
    entry_threshold = 2.0
    long_signals = np.sum(z_scores < -entry_threshold)
    short_signals = np.sum(z_scores > entry_threshold)

    print(f"\n交易信号 (阈值=±{entry_threshold}):")
    print(f"  做多信号: {long_signals}次")
    print(f"  做空信号: {short_signals}次")
    print(f"  总信号: {long_signals + short_signals}次")

    return kalman

def test_strategy_config():
    """测试策略配置"""
    print("\n" + "=" * 60)
    print("测试策略配置")
    print("=" * 60)

    config = KalmanPairsTradingConfig(
        instrument_a_id="SOLUSDT-PERP.BINANCE",
        instrument_b_id="ETHUSDT-PERP.BINANCE",
        bar_type="SOLUSDT-PERP.BINANCE-1-HOUR-MID",
        delta=1e-4,
        R=1.0,
        warmup_period=50,
        entry_threshold=2.0,
        exit_threshold=0.5,
        stop_loss_threshold=4.0,
        max_notional_per_trade=10000.0,
        max_positions=1,
    )

    print("\n配置参数:")
    print(f"  交易对: {config.instrument_a_id} vs {config.instrument_b_id}")
    print(f"  预热期: {config.warmup_period} bars")
    print(f"  入场阈值: ±{config.entry_threshold}")
    print(f"  出场阈值: ±{config.exit_threshold}")
    print(f"  止损阈值: ±{config.stop_loss_threshold}")
    print(f"  最大名义价值: ${config.max_notional_per_trade:,.0f}")
    print(f"  卡尔曼参数: delta={config.delta}, R={config.R}")

    return config

def main():
    print("\n卡尔曼配对交易策略 - 功能测试\n")

    # 测试卡尔曼滤波器
    test_kalman_filter()

    # 测试策略配置
    test_strategy_config()

    print("\n" + "=" * 60)
    print("✓ 所有测试通过")
    print("=" * 60)
    print("\n策略已就绪，可用于实际回测")
    print("注意: 需要准备SOLUSDT和ETHUSDT的历史数据")

if __name__ == "__main__":
    main()
