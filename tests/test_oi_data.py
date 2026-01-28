"""
OI 数据获取验证脚本

测试 Open Interest 和 Funding Rate 数据的获取、加载和验证功能。
"""

import sys
from decimal import Decimal
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from nautilus_trader.model.identifiers import InstrumentId

from utils.custom_data import FundingRateData, OpenInterestData
from utils.oi_funding_adapter import OIFundingDataLoader


def test_custom_data_creation():
    """测试自定义数据类型的创建"""
    print("\n" + "=" * 60)
    print("测试 1: 自定义数据类型创建")
    print("=" * 60)

    # 创建 InstrumentId
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")

    # 创建 OpenInterestData
    oi_data = OpenInterestData(
        instrument_id=instrument_id,
        open_interest=Decimal("1000000.5"),
        ts_event=1640000000000000000,  # 纳秒
        ts_init=1640000000000000000,
    )

    print(f"✅ OpenInterestData 创建成功:")
    print(f"   {oi_data}")

    # 创建 FundingRateData
    funding_data = FundingRateData(
        instrument_id=instrument_id,
        funding_rate=Decimal("0.0001"),
        next_funding_time=None,
        ts_event=1640000000000000000,
        ts_init=1640000000000000000,
    )

    print(f"✅ FundingRateData 创建成功:")
    print(f"   {funding_data}")
    print(f"   年化费率: {funding_data.funding_rate_annual:.2f}%")

    return True


def test_oi_data_loader():
    """测试 OI 数据加载器"""
    print("\n" + "=" * 60)
    print("测试 2: OI 数据加载器")
    print("=" * 60)

    # 初始化加载器
    base_dir = Path(__file__).parent.parent
    loader = OIFundingDataLoader(base_dir)

    print(f"✅ 数据加载器初始化成功")
    print(f"   基础目录: {base_dir}")
    print(f"   数据目录: {loader.data_dir}")

    # 检查数据目录是否存在
    if not loader.data_dir.exists():
        print(f"⚠️  数据目录不存在: {loader.data_dir}")
        print(f"   请先运行数据获取脚本")
        return False

    # 列出可用的数据文件
    print(f"\n📁 可用的数据文件:")
    for symbol_dir in loader.data_dir.iterdir():
        if symbol_dir.is_dir():
            print(f"   {symbol_dir.name}/")
            for data_file in symbol_dir.iterdir():
                if data_file.suffix == ".csv":
                    print(f"     - {data_file.name}")

    return True


def test_load_sample_data():
    """测试加载示例数据"""
    print("\n" + "=" * 60)
    print("测试 3: 加载示例数据")
    print("=" * 60)

    base_dir = Path(__file__).parent.parent
    loader = OIFundingDataLoader(base_dir)

    # 尝试加载 BTCUSDT 数据
    symbol = "BTCUSDT"
    instrument_id = InstrumentId.from_str("BTCUSDT.BINANCE")

    # 使用实际存在的数据文件日期范围
    start_date = "2025-12-22"
    end_date = "2026-01-21"

    print(f"📊 尝试加载数据:")
    print(f"   交易对: {symbol}")
    print(f"   日期范围: {start_date} ~ {end_date}")

    # 加载 OI 数据
    oi_data = loader.load_oi_data(
        symbol=symbol,
        instrument_id=instrument_id,
        start_date=start_date,
        end_date=end_date,
        exchange="binance",
        period="1h",
    )

    if oi_data:
        print(f"✅ OI 数据加载成功: {len(oi_data)} 条记录")
        print(f"   第一条: {oi_data[0]}")
        print(f"   最后一条: {oi_data[-1]}")
    else:
        print(f"⚠️  未找到 OI 数据文件")

    # 加载 Funding Rate 数据
    funding_data = loader.load_funding_data(
        symbol=symbol,
        instrument_id=instrument_id,
        start_date=start_date,
        end_date=end_date,
        exchange="binance",
    )

    if funding_data:
        print(f"✅ Funding Rate 数据加载成功: {len(funding_data)} 条记录")
        print(f"   第一条: {funding_data[0]}")
        print(f"   最后一条: {funding_data[-1]}")
    else:
        print(f"⚠️  未找到 Funding Rate 数据文件")

    return len(oi_data) > 0 or len(funding_data) > 0


def test_data_validation():
    """测试数据验证功能"""
    print("\n" + "=" * 60)
    print("测试 4: 数据验证")
    print("=" * 60)

    from utils.data_validator import FundingRateValidator, OIValidator

    # 测试 OI 验证器
    oi_validator = OIValidator(spike_threshold=0.5, enable_logging=False)

    # 测试有效数据
    is_valid, error = oi_validator.validate(Decimal("1000000"))
    print(f"✅ OI 验证器 - 有效数据: {is_valid}")

    # 测试无效数据（0）
    is_valid, error = oi_validator.validate(Decimal("0"))
    print(f"✅ OI 验证器 - 无效数据（0）: {is_valid}, 错误: {error}")

    # 测试 Funding Rate 验证器
    funding_validator = FundingRateValidator(
        max_abs_value=500.0,
        spike_threshold=200.0,
        enable_logging=False,
    )

    # 测试有效数据
    is_valid, error = funding_validator.validate(Decimal("30.5"))
    print(f"✅ Funding Rate 验证器 - 有效数据: {is_valid}")

    # 测试异常数据（超过阈值）
    is_valid, error = funding_validator.validate(Decimal("600.0"))
    print(f"✅ Funding Rate 验证器 - 异常数据: {is_valid}, 错误: {error}")

    return True


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("🚀 OI 数据获取验证测试")
    print("=" * 60)

    results = []

    # 运行测试
    try:
        results.append(("自定义数据类型创建", test_custom_data_creation()))
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results.append(("自定义数据类型创建", False))

    try:
        results.append(("OI 数据加载器", test_oi_data_loader()))
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results.append(("OI 数据加载器", False))

    try:
        results.append(("加载示例数据", test_load_sample_data()))
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results.append(("加载示例数据", False))

    try:
        results.append(("数据验证", test_data_validation()))
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        results.append(("数据验证", False))

    # 输出测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {test_name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit(main())
