"""
数据质量检查示例

演示如何使用DataManager进行数据质量检查
"""

from pathlib import Path
import pandas as pd

from utils.data_management.data_manager import DataManager, DataQualityChecker


def example_basic_quality_check():
    """示例1: 基础数据质量检查"""
    print("=" * 60)
    print("示例1: 基础数据质量检查")
    print("=" * 60)

    # 创建质量检查器
    checker = DataQualityChecker(enable_logging=True)

    # 创建测试数据
    start_ms = 1609459200000  # 2021-01-01 00:00:00
    timestamps = [start_ms + i * 3600000 for i in range(24)]

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": [50000 + i * 10 for i in range(24)],
        "high": [50100 + i * 10 for i in range(24)],
        "low": [49900 + i * 10 for i in range(24)],
        "close": [50050 + i * 10 for i in range(24)],
        "volume": [1000 + i * 50 for i in range(24)],
    })

    # 执行质量检查
    is_valid, issues = checker.validate_data_quality(
        df, "BTCUSDT", "1h", "2021-01-01", "2021-01-02"
    )

    print(f"\n数据质量检查结果: {'✓ 通过' if is_valid else '✗ 失败'}")
    if issues:
        print("发现的问题:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("未发现任何问题")


def example_detect_missing_values():
    """示例2: 检测缺失值"""
    print("\n" + "=" * 60)
    print("示例2: 检测缺失值")
    print("=" * 60)

    checker = DataQualityChecker(enable_logging=True)

    # 创建有缺失值的数据
    df = pd.DataFrame({
        "timestamp": [1000, 2000, 3000, 4000, 5000],
        "open": [100, 101, None, 103, 104],
        "high": [105, 106, 107, None, 109],
        "low": [95, 96, 97, 98, 99],
        "close": [102, 103, 104, 105, 106],
        "volume": [1000, 1100, 1200, 1300, 1400],
    })

    issues = checker.check_missing_values(df, "BTCUSDT")
    print(f"\n缺失值检查: 发现 {len(issues)} 个问题")
    for issue in issues:
        print(f"  - {issue}")


def example_detect_timestamp_gaps():
    """示例3: 检测时间戳间隔"""
    print("\n" + "=" * 60)
    print("示例3: 检测时间戳间隔")
    print("=" * 60)

    checker = DataQualityChecker(enable_logging=True)

    # 创建有时间间隔的数据
    df = pd.DataFrame({
        "timestamp": [
            1000000,
            1000000 + 3600000,  # +1小时
            1000000 + 7200000,  # +2小时
            1000000 + 14400000,  # +4小时（跳过了3小时）
            1000000 + 18000000,  # +5小时
        ],
        "close": [100, 101, 102, 103, 104],
    })

    issues = checker.check_timestamp_continuity(df, "BTCUSDT", "1h")
    print(f"\n时间戳连续性检查: 发现 {len(issues)} 个问题")
    for issue in issues:
        print(f"  - {issue}")


def example_detect_price_outliers():
    """示例4: 检测价格异常值"""
    print("\n" + "=" * 60)
    print("示例4: 检测价格异常值")
    print("=" * 60)

    checker = DataQualityChecker(enable_logging=True)

    # 创建有价格异常的数据
    normal_prices = [100 + i * 0.1 for i in range(50)]
    # 插入异常值
    normal_prices[25] = 200  # 突然翻倍

    df = pd.DataFrame({"close": normal_prices})

    issues = checker.check_price_outliers(df, "BTCUSDT", sigma=3.0)
    print(f"\n价格异常值检查: 发现 {len(issues)} 个问题")
    for issue in issues:
        print(f"  - {issue}")


def example_detect_volume_anomalies():
    """示例5: 检测成交量异常"""
    print("\n" + "=" * 60)
    print("示例5: 检测成交量异常")
    print("=" * 60)

    checker = DataQualityChecker(enable_logging=True)

    # 创建有零成交量的数据
    df = pd.DataFrame({
        "volume": [1000, 0, 0, 0, 0, 0, 0, 1000, 1000, 1000],
    })

    issues = checker.check_volume_anomalies(df, "BTCUSDT", zero_threshold=0.05)
    print(f"\n成交量异常检查: 发现 {len(issues)} 个问题")
    for issue in issues:
        print(f"  - {issue}")


def example_batch_validation():
    """示例6: 批量验证数据"""
    print("\n" + "=" * 60)
    print("示例6: 批量验证数据（需要实际数据文件）")
    print("=" * 60)

    base_dir = Path(".")
    manager = DataManager(base_dir, enable_quality_check=True)

    # 注意：这需要实际的数据文件存在
    # 这里仅作为示例代码
    print("\n提示: 此示例需要实际数据文件，跳过执行")
    print("使用方法:")
    print("""
    result = manager.batch_validate_data(
        symbols=["BTCUSDT", "ETHUSDT"],
        start_date="2024-01-01",
        end_date="2024-12-31",
        timeframe="1h",
        exchange="binance"
    )

    print(f"通过: {result['passed']}")
    print(f"失败: {result['failed']}")
    """)


def main():
    """运行所有示例"""
    print("\n" + "=" * 60)
    print("数据质量检查系统示例")
    print("=" * 60)

    example_basic_quality_check()
    example_detect_missing_values()
    example_detect_timestamp_gaps()
    example_detect_price_outliers()
    example_detect_volume_anomalies()
    example_batch_validation()

    print("\n" + "=" * 60)
    print("所有示例执行完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
